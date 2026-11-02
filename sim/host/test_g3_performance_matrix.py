#!/usr/bin/env python3
"""性能矩阵编排回归；客户端/LDPC为显式测试替身，不连接板子。"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'tools/board'))
spec=importlib.util.spec_from_file_location('g3_performance_matrix',REPO/'tools/board/g3_performance_matrix.py')
matrix=importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)

VOTER=b'[HW-CYCLES] Stage2 Voter: total 10000 cyc (0.100 ms), init 810, read 220, vote 330, write 440\n\r'
DECODER=b'[HW-CYCLES] Stage3 Decoder: total 20000 cyc (0.200 ms), rd_busy 20, wr_busy 30, rd_wait 40\n\r'

class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='g3-perf-host-')
        self.root=Path(self.temp.name)
        self.reads=self.root/'reads.fastq'
        self.reads.write_text('@read\nACGT\n+\nIIII\n'*64)
        self.wm=self.root/'wm.txt';self.wm.write_text('ACGT')
        self.uart=self.root/'uart.log';self.uart.write_bytes(b'old task\n'+VOTER+DECODER)
        self.image=b'explicit host fake image'
        self.configs=[]
    def tearDown(self):self.temp.cleanup()
    def client(self,cfg):
        self.configs.append(cfg)
        cfg.out.write_text('0'*64800+'\n')
        with self.uart.open('ab') as stream:stream.write(VOTER+DECODER)
        return SimpleNamespace(t_result=1+cfg.send_limit*.001,t_wm=.01,t_batches=.02,t_total=1.5)
    def decode(self,command,**kwargs):
        self.assertEqual(command[2],'decode')
        Path(command[command.index('--image')+1]).write_bytes(self.image)
        Path(command[command.index('-o')+1]).write_text('fixture')
        return SimpleNamespace(returncode=0)
    def run_matrix(self,*,full_correct=True,client=None,limits='13,full'):
        out=self.root/'out'
        argv=['matrix','--artifact-dir',str(self.root/'artifacts'),'--out-dir',str(out),
              '--reads',str(self.reads),'--watermark',str(self.wm),'--limits',limits,
              '--uart-log',str(self.uart),'--repeat','3','--ip','127.0.0.1']
        expected=hashlib.sha256(self.image).hexdigest() if full_correct else 'f'*64
        with patch.object(sys,'argv',argv),patch.object(matrix,'validate',return_value={'_ps7':b'fake','board_id':'fake-host-only'}),\
             patch.object(matrix,'query_board_caps',return_value=SimpleNamespace(version=1,read_bps=150,num_lc=50,stride=807,max_symbols=40500,max_reads=129600,features=1)),\
             patch.object(matrix,'run_client',side_effect=client or self.client),\
             patch.object(matrix.subprocess,'run',side_effect=self.decode),\
             patch.object(matrix.time,'sleep'),patch.object(matrix,'EXPECT_SHA',expected),\
             contextlib.redirect_stdout(io.StringIO()):
            status=matrix.main()
        rows=[json.loads(line) for line in (out/'samples.jsonl').read_text().splitlines()]
        return status,rows,json.loads((out/'summary.json').read_text())
    def test_uart_only_current_sample(self):
        offset=self.uart.stat().st_size
        with self.uart.open('ab') as stream:stream.write(VOTER+DECODER)
        values,note=matrix.read_uart_cycles(self.uart,offset)
        self.assertEqual(values['stage2_voter']['total'],10000)
        self.assertEqual(values['stage3_decoder']['rd_wait'],40)
        self.assertIsNone(values['stage1'])
        self.assertTrue(note.startswith('MEASURED'))
    def test_duplicate_uart_tasks_refused(self):
        self.uart.write_bytes(VOTER+DECODER+VOTER+DECODER)
        values,note=matrix.read_uart_cycles(self.uart,0)
        self.assertIsNone(values)
        self.assertIn('记录数=2',note)
    def test_missing_uart_truthful(self):
        values,note=matrix.read_uart_cycles(None,0)
        self.assertIsNone(values)
        self.assertIn('已有Stage2/3',note)
    def test_client_decode_and_exact_padding(self):
        status,rows,summary=self.run_matrix()
        self.assertEqual(status,0);self.assertEqual(len(rows),6)
        self.assertEqual([r['record_count'] for r in rows],[64]*3+[128]*3)
        self.assertEqual(rows[0]['functional_status'],'NOT_REQUIRED_PARTIAL_INPUT')
        self.assertEqual(rows[3]['functional_status'],'PASS')
        self.assertTrue(all(r['hardware_cycles']['stage2_voter']['total']==10000 for r in rows))
        self.assertEqual(len(self.configs),6)
        self.assertTrue(all(c.orient=='both' and c.read_bps==150 and c.score_min==67 for c in self.configs))
        self.assertAlmostEqual(summary['fit']['slope_s_per_record'],.051/64)
    def test_full_hash_failure_excluded_from_fit(self):
        status,rows,summary=self.run_matrix(full_correct=False)
        self.assertEqual(status,1)
        self.assertTrue(all(r['status']=='FAIL' for r in rows[3:]))
        self.assertEqual(len(summary['sizes']),1)
        self.assertIsNone(summary['fit'])
    def test_invalid_timing_cannot_pass(self):
        def invalid(cfg):
            stats=self.client(cfg);stats.t_result=float('nan');return stats
        status,rows,summary=self.run_matrix(client=invalid)
        self.assertEqual(status,1)
        self.assertEqual(summary['sizes'],[])
        self.assertTrue(all(r['status']=='FAIL' and '有限正数' in r['error'] for r in rows))
    def test_same_padded_sizes_rejected_before_board(self):
        with self.assertRaises(SystemExit) as error,contextlib.redirect_stderr(io.StringIO()):
            self.run_matrix(limits='13,20')
        self.assertEqual(error.exception.code,2)
        self.assertEqual(self.configs,[])

if __name__=='__main__':unittest.main()

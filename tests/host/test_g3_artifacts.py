#!/usr/bin/env python3
"""不连接硬件的G3制品/路径/串口/计划入口负用例。"""
import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
import zipfile
import sys
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('g3_artifacts',REPO/'tools/board/g3_artifacts.py')
g3=importlib.util.module_from_spec(spec);spec.loader.exec_module(g3)

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='g3-static-')
        self.root=Path(self.temp.name)
        self.params=dict(zip(g3.PARAMS,(150,50,807,957,64,16,1)))
        self.part='xc7z020clg400-2'
        self.manifest={'schema_version':1,'board_id':'bkb220','part':self.part,
            'parameters':copy.deepcopy(self.params),'artifacts':g3.LEGACY_FILES.copy(),
            'tool_versions':{'vivado':'2026.1','vitis':'2026.1'},
            'source_manifest':{'path':'source_manifest.json','sha256':''}}
        self.source={'files':{'hw/scripts/bd.tcl':'a'*64}}
        self.xsa_params=copy.deepcopy(self.params)
        self.xsa_part=self.part
        self.embedded_bit=b'fixture-bit-only'
        self.include_system=True
        self.write()
    def tearDown(self):self.temp.cleanup()
    def write(self):
        for k,n in g3.LEGACY_FILES.items():
            if k!='xsa':(self.root/n).write_bytes(self.embedded_bit if k=='bit' else b'fixture-'+k.encode())
        info={'devices':[{'part':{'name':self.xsa_part}}],'files':[{'name':'inside.bit','type':'FULL_BIT'}],'generatedVersion':'2026.1'}
        system=f'<SYSTEMINFO DEVICE="{self.xsa_part[2:7]}" PACKAGE="clg400" SPEEDGRADE="-2"/>' if self.include_system else ''
        hwh=f'<EDKSYSTEM>{system}<MODULE MODTYPE="Dna_accelerator_core"><PARAMETERS>'
        hwh+=''.join(f'<PARAMETER NAME="{k}" VALUE="{v}"/>' for k,v in self.xsa_params.items())
        hwh+='</PARAMETERS></MODULE></EDKSYSTEM>'
        with zipfile.ZipFile(self.root/g3.LEGACY_FILES['xsa'],'w') as z:
            z.writestr('xsa.json',json.dumps(info));z.writestr('ps7_init.tcl','fixture-init')
            z.writestr('inside.bit',self.embedded_bit);z.writestr('system.hwh',hwh)
        (self.root/'source_manifest.json').write_text(json.dumps(self.source))
        self.manifest['source_manifest']['sha256']=g3.sha(self.root/'source_manifest.json')
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))
        self.sums()
    def sums(self):
        (self.root/'SHA256SUMS').write_text(''.join(f'{g3.sha(p)}  {p.name}\n' for p in sorted(self.root.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    def rejected(self,pattern,**kw):
        with self.assertRaisesRegex(ValueError,pattern):g3.validate(self.root,**kw)
    def test_valid(self):
        info=g3.validate(self.root,device='xc7z020');self.assertEqual(info['parameters']['C_STAGE1_P_WAYS'],16)
    def test_wrong_target(self):self.rejected('目标器件',device='xc7z010')
    def test_missing_xsa(self):
        (self.root/g3.LEGACY_FILES['xsa']).unlink();self.rejected('不存在')
    def test_missing_manifest(self):
        (self.root/'manifest.json').unlink();self.sums();self.rejected('缺 manifest')
    def test_legacy_z020_refused(self):
        (self.root/'manifest.json').unlink();self.sums();self.rejected('只允许旧',allow_legacy=True)
    def test_hash_failure(self):
        (self.root/g3.LEGACY_FILES['elf']).write_bytes(b'wrong');self.rejected('校验失败')
    def test_missing_hash_entry(self):
        p=self.root/'SHA256SUMS';p.write_text('\n'.join(l for l in p.read_text().splitlines() if 'fsbl.elf' not in l));self.rejected('未被 SHA256SUMS')
    def test_embedded_bit_mismatch(self):
        (self.root/g3.LEGACY_FILES['bit']).write_bytes(b'other-bit');self.sums();self.rejected('内置 bit')
    def test_part_manifest_mismatch(self):
        self.manifest['part']='xc7z010clg400-1';self.write();self.rejected('part 与 XSA')
    def test_param_mismatch(self):
        self.manifest['parameters']['C_STAGE1_P_WAYS']=4;self.write();self.rejected('参数与 XSA')
    def test_missing_pway_evidence(self):
        del self.xsa_params['C_STAGE1_PIPE_TREE'];self.write();self.rejected('参数与 XSA')
    def test_wrong_geometry_self_consistent(self):
        self.params['NUM_LC']=6;self.manifest['parameters']['NUM_LC']=6;self.xsa_params['NUM_LC']=6;self.write();self.rejected('正式生产几何')
    def test_wrong_architecture_self_consistent(self):
        self.manifest['parameters']['C_STAGE1_PIPE_TREE']=0;self.xsa_params['C_STAGE1_PIPE_TREE']=0;self.write();self.rejected('P4/0或P16/1')
    def test_source_manifest_list_refused(self):
        self.source['files']=['looks-present'];self.write();self.rejected('路径->SHA256字典')
    def test_source_manifest_bad_hash(self):
        self.source['files']={'hw/file.v':'bad'};self.write();self.rejected('非法SHA256')
    def test_source_manifest_escape(self):
        self.source['files']={'../hw/file.v':'a'*64};self.write();self.rejected('非法源码')
    def test_tool_versions_list_refused(self):
        self.manifest['tool_versions']=['2026.1'];self.write();self.rejected('tool_versions必须')
    def test_tool_versions_blank_refused(self):
        self.manifest['tool_versions']={'vivado':' '};self.write();self.rejected('tool_versions必须')
    def test_missing_vitis_version(self):
        self.manifest['tool_versions']={'vivado':'2026.1'};self.write();self.rejected('可核验vivado/vitis')
    def test_wrong_vivado_version(self):
        self.manifest['tool_versions']['vivado']='2022.2';self.write();self.rejected('generatedVersion')
    def test_missing_systeminfo(self):
        self.include_system=False;self.write();self.rejected('缺少 SYSTEMINFO')
    def test_stage_same_dir_rejected(self):
        p=subprocess.run(['python3',str(REPO/'tools/board/g3_artifacts.py'),'--artifact-dir',str(self.root),'--stage',str(self.root)],capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertIn('不得等于',p.stderr)
    def test_stage_extracts_selected_init(self):
        dest=self.root.parent/(self.root.name+'-stage')
        # 独立TemporaryDirectory保留退出清理，stage内部只有本用例新生成文件。
        with tempfile.TemporaryDirectory(prefix='g3-stage-') as temp_stage:
            p=subprocess.run(['python3',str(REPO/'tools/board/g3_artifacts.py'),'--artifact-dir',str(self.root),'--stage',temp_stage],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual((Path(temp_stage)/'ps7_init.tcl').read_text(),'fixture-init')
    def test_plan_new_no_hardware(self):
        p=self.plan('--device','xc7z020');self.assertEqual(p.returncode,0,p.stderr);self.assertIn('不打开串口',p.stdout)
    def test_plan_wrong_target(self):
        p=self.plan('--device','xc7z010');self.assertEqual(p.returncode,2);self.assertIn('目标器件',p.stderr)
    def test_plan_missing_tool(self):
        p=self.plan('--xsdb','Z:/missing-tool/xsdb.bat',skip_tools=False);self.assertEqual(p.returncode,2);self.assertIn('找不到 XSDB',p.stderr)
    def test_plan_bad_path(self):
        p=self.plan('--win-root','relative/path');self.assertEqual(p.returncode,2);self.assertIn('路径转换失败',p.stderr)
    def test_single_bit_override_refused(self):
        p=self.root/'separate.bit';p.write_bytes(b'other');self.rejected('覆盖 bit',bit_override=str(p))
    def test_plan_legacy_default(self):
        p=subprocess.run(['bash','tools/run_g3.sh','--plan-only','--skip-boot','--skip-dump','--no-uart'],cwd=REPO,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('legacy',p.stdout)
    def plan(self,*extra,skip_tools=True):
        cmd=['bash','tools/run_g3.sh','--artifact-dir',str(self.root),'--plan-only','--no-uart']
        if skip_tools:cmd+=['--skip-boot','--skip-dump']
        return subprocess.run(cmd+list(extra),cwd=REPO,capture_output=True,text=True)

class SelectionTests(unittest.TestCase):
    def test_path_windows(self):self.assertEqual(g3.normalize_windows_path(r'D:\xilinx tools\2026.1\xsdb.bat'),('D:/xilinx tools/2026.1/xsdb.bat','/mnt/d/xilinx tools/2026.1/xsdb.bat'))
    def test_path_wsl(self):self.assertEqual(g3.normalize_windows_path('/mnt/e/build folder'),('E:/build folder','/mnt/e/build folder'))
    def test_relative_path_refused(self):
        with self.assertRaises(ValueError):g3.normalize_windows_path('relative/xsdb.bat')
    def test_bluetooth_not_auto(self):
        with self.assertRaises(ValueError):g3.choose_uart([{'FriendlyName':'Bluetooth(COM6)','InstanceId':'BTHENUM\\1'}])
    def test_usb_unique(self):self.assertEqual(g3.choose_uart([{'FriendlyName':'CH340 (COM6)','InstanceId':'USB\\VID_1'}]),'COM6')
    def test_ftdi_multiple_explicit(self):
        ports=[{'FriendlyName':f'USB Serial Port (COM{i})','InstanceId':f'FTDIBUS\\{i}'} for i in (7,8)]
        with self.assertRaises(ValueError):g3.choose_uart(ports)
        self.assertEqual(g3.choose_uart(ports,'COM8'),'COM8')
    def test_explicit_bluetooth_refused(self):
        with self.assertRaises(ValueError):g3.choose_uart([{'FriendlyName':'Bluetooth (COM6)','InstanceId':'BTHENUM\\1'}],'COM6')

class MeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(REPO/'tools/board'))
        import g3_performance_matrix
        cls.matrix=g3_performance_matrix
    def test_fit_true_model(self):
        rows=[{'record_count':n,'t_result_median_s':0.5+0.000079*n} for n in (256,1024,4096,16384,65536,103616)]
        result=self.matrix.fit(rows)
        self.assertAlmostEqual(result['intercept_s'],0.5)
        self.assertAlmostEqual(result['slope_s_per_record'],0.000079)
        self.assertAlmostEqual(result['r2'],1)
    def test_fit_one_size_rejected(self):
        with self.assertRaises(ValueError):self.matrix.fit([{'record_count':64,'t_result_median_s':1}])
    def test_fit_same_padded_size_rejected(self):
        with self.assertRaises(ValueError):self.matrix.fit([{'record_count':64,'t_result_median_s':t} for t in (1,2)])
    def test_fastq_incomplete_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reads.fastq';p.write_text('@read\nAAA\n+\n')
            with self.assertRaises(ValueError):self.matrix.count_reads(p)

if __name__=='__main__':unittest.main(verbosity=2)

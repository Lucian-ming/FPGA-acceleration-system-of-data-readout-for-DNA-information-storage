"""Check actual launcher selection with fake Vivado, never start EDA."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
LAUNCHER=ROOT/'tools/run_vivado_build.sh'

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vivado-launcher-')
        self.base=Path(self.temp.name)
        self.record=self.base/'selected.txt'
        self.environment=os.environ.copy()
        for key in ['VIVADO','VIVADO_ROOT']:self.environment.pop(key,None)
        self.environment['VIVADO_LOG_ROOT']=str(self.base/'logs')
        self.environment['TEST_VIVADO_RECORD']=str(self.record)
        self.on_path=self.fake('path tools','path')
        self.environment['PATH']=str(self.on_path.parent)+os.pathsep+self.environment['PATH']
        self.root_tool=self.fake('root with spaces/bin','root')
    def tearDown(self):self.temp.cleanup()
    def fake(self,folder,label):
        path=self.base/folder/'vivado';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#!/bin/sh\nprintf "%s\\n" "'+label+'" "$@" > "$TEST_VIVADO_RECORD"\n')
        path.chmod(0o755);return path
    def run_launcher(self,*args):
        return subprocess.run(['bash',str(LAUNCHER),*args],cwd=self.base,env=self.environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
    def test_explicit_root_wins_over_path(self):
        self.environment['VIVADO_ROOT']=str(self.root_tool.parent.parent)
        result=self.run_launcher('board=zynq_eco_7010','dry_run=1')
        self.assertEqual(result.returncode,0,result.stdout)
        lines=self.record.read_text().splitlines()
        self.assertEqual(lines[0],'root')
        self.assertIn(str(ROOT/'hw/scripts/build.tcl'),lines)
        self.assertIn('dry_run=1',lines)
    def test_explicit_binary_wins_over_root(self):
        self.environment['VIVADO_ROOT']=str(self.root_tool.parent.parent)
        self.environment['VIVADO']=str(self.fake('explicit tools','explicit'))
        result=self.run_launcher('board=zynq_eco_7010','dry_run=1')
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(self.record.read_text().splitlines()[0],'explicit')
    def test_invalid_explicit_root_never_falls_back_to_path(self):
        self.environment['VIVADO_ROOT']=str(self.base/'missing')
        result=self.run_launcher('dry_run=1')
        self.assertEqual(result.returncode,127,result.stdout)
        self.assertFalse(self.record.exists())
    def test_help_does_not_need_tool(self):
        self.environment['VIVADO_ROOT']=str(self.base/'missing')
        result=self.run_launcher('--help')
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertIn('2022.2',result.stdout)
        self.assertFalse(self.record.exists())

if __name__=='__main__':unittest.main(verbosity=2)

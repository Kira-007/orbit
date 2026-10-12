"""Exercise install/reinstall/uninstall against an isolated HOME, without a live reload."""
import os,pathlib,runpy,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
class InstallTest(unittest.TestCase):
 def test_round_trip(self):
  with tempfile.TemporaryDirectory(prefix='orbit user ') as tmp:
   home=pathlib.Path(tmp);config=home/'.config/hypr/hyprland.lua';config.parent.mkdir(parents=True);config.write_text('-- existing config\n')
   claude=home/'.claude/settings.json';claude.parent.mkdir();claude.write_text('{"model":"keep"}')
   env={'HOME':str(home),'XDG_CONFIG_HOME':str(home/'.config'),'XDG_DATA_HOME':str(home/'.local/share'),'XDG_STATE_HOME':str(home/'.local/state')}
   def run(cmd,**kwargs):
    import subprocess
    return subprocess.CompletedProcess(cmd,0,stdout='' if cmd[1]=='configerrors' else 'ok\n',stderr='')
   sys.path.insert(0,str(ROOT))
   with patch.dict(os.environ,env),patch('shutil.which',return_value='/bin/tool'),patch('subprocess.run',side_effect=run):
    sys.modules.pop('integration',None)
    for _ in range(2):
     with patch.object(sys,'argv',['install.py','--hooks']):runpy.run_path(str(ROOT/'install.py'),run_name='__main__')
    self.assertEqual(config.read_text().count('-- BEGIN Orbit portable'),1)
    self.assertTrue((home/'.local/share/applications/orbit.desktop').exists())
    with patch.object(sys,'argv',['uninstall.py']):runpy.run_path(str(ROOT/'uninstall.py'),run_name='__main__')
    self.assertEqual(config.read_text().strip(),'-- existing config')
    import json
    self.assertEqual(json.loads(claude.read_text())['model'],'keep')
    self.assertNotIn('emit.py',claude.read_text())
    self.assertFalse((home/'.local/share/applications/orbit.desktop').exists())
   sys.path.remove(str(ROOT));sys.modules.pop('integration',None)
if __name__=='__main__':unittest.main()

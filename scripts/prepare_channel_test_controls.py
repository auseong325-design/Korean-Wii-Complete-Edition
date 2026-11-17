"""Configure clear A/HOME aliases in stopped, dedicated test profiles only."""
from prepare_channel_access import CHANNELS,ROOT,stopped
import re

def main():
 stopped()
 for channel in CHANNELS:
  path=ROOT/f'workspace/sandbox/{channel}-test-v1/user/Config/WiimoteNew.ini'
  data=path.read_text(encoding='utf-8-sig')
  data=re.sub(r'^Buttons/A\s*=.*$', 'Buttons/A = `Click 0` | pulse(`Click 2` | SPACE, 0.25)',data,flags=re.M)
  data=re.sub(r'^Buttons/B\s*=.*$', 'Buttons/B = `Click 1` | pulse(X, 0.25)',data,flags=re.M)
  data=re.sub(r'^Buttons/Home\s*=.*$', 'Buttons/Home = RETURN',data,flags=re.M)
  for axis in 'XYZ':data=re.sub(r'^Shake/'+axis+r'\s*=.*$', 'Shake/'+axis+' =',data,flags=re.M)
  path.write_text(data,encoding='utf-8')
 print('Test controls: A left/middle/Space (250 ms pulse), B right/X, A+B Space+X, HOME Return; middle shake removed')

if __name__=='__main__':main()

"""Enable private SDK diagnostic logging only in the stopped Nintendo test."""
import configparser
from prepare_channel_access import ROOT,stopped

def main():
 stopped();p=ROOT/'workspace/sandbox/nintendo-test-v1/user/Config/Logger.ini'
 c=configparser.ConfigParser();c.optionxform=str;c.read(p,encoding='utf-8-sig')
 for k in ['OSREPORT','OSREPORT_HLE']:c['Logs'][k]='True'
 c['Options']['Verbosity']='4'
 with p.open('w',encoding='utf-8')as f:c.write(f)
 print('Nintendo test SDK diagnostics enabled; raw output stays in private local logs')

if __name__=='__main__':main()

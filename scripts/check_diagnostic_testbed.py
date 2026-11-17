"""Check sanitized evidence produced by the synthetic-only Dolphin test bed."""
from audit_sd import ROOT

def main():
    path=ROOT/'workspace/sandbox/hardware-test-v1/sd-sync/kwce/diagnostics/diag-0003.txt'
    lines=path.read_text(encoding='ascii').splitlines()
    if lines[0]!='KWCE_DIAGNOSTIC_V1':raise ValueError('Diagnostic marker')
    rows=[line.split('=',1) for line in lines[1:]]
    data={k:v for k,v in rows};expected={'phase':'after_news','news_installed_build':'news_r22','room_installed_build':'room_r51','wc24_list_format':'recognized_v1','wc24_list_read_result':'63488','task_0_channel':'news','task_0_error_count':'7','task_0_error_code':'-106','task_1_channel':'wii_room','task_1_error_count':'3','task_1_error_code':'-42','matched_task_count':'2','stage':'complete'}
    for k,v in expected.items():
        if data.get(k)!=v:raise ValueError('Unexpected diagnostic output: '+k)
    base={'phase','stage','wii_clock_unix','ios_version','conf_init_result','area','language','wc24_enabled','news_installed_tmd_version','room_installed_tmd_version','forecast_installed_tmd_version','news_installed_build','room_installed_build','isfs_init_result','wc24_list_open_result','wc24_list_read_result','wc24_list_format','matched_task_count','news_cache_open_result','news_cache_stat_result','news_cache_bytes','news_dir_result','news_dir_entries','room_dir_result','room_dir_entries'}
    fields={'channel','flags','error_count','error_code','remaining_downloads','retry_minutes','subtask_mask','last_download_minutes_2000','route'}
    allowed=base|{f'task_{n}_{name}' for n in (0,1) for name in fields}
    if any(k not in allowed for k,_ in rows):raise ValueError('Unexpected report field')
    room=path.with_name('diag-0004.txt').read_text(encoding='ascii')
    if 'phase=after_room\n' not in room or 'stage=complete\n' not in room:raise ValueError('Room phase snapshot missing')
    print('PASS: News/Room snapshots, build identification, synthetic errors, sanitized field allowlist, distinct report files')
if __name__=='__main__':main()

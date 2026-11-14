"""Audit `.replay` and TAS `.data` files before labels are generated.

No attempt is made to infer TAS control field names.  All paths remain local.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from collections import Counter


def audit_replays(directory):
    paths = sorted(Path(directory).rglob('*.replay'))
    hashes = Counter()
    entries = []
    for path in paths:
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        hashes[sha] += 1
        # UE3 .replay uses a length-prefixed header with a following checksum.
        # A plausible header is NOT validation: replicar must decode the file.
        hdr = struct.unpack_from('<I', data)[0] if len(data) >= 4 else 0
        plausible = len(data) >= 128 and 0 < hdr <= len(data) - 8
        entries.append({'file': str(path), 'sha256': sha,
                        'size': len(data), 'header_plausible': plausible})
    return {'count': len(paths), 'unique_by_sha256': len(hashes),
            'duplicate_files': sum(n-1 for n in hashes.values()),
            'below_100kb': sum(x['size'] < 100000 for x in entries),
            'plausible_header_count': sum(x['header_plausible'] for x in entries),
            'files': entries}


def audit_tas(directory):
    paths = sorted(Path(directory).rglob('*.data'))
    entries=[]
    for path in paths:
        data=path.read_bytes()
        version,count=struct.unpack_from('<II',data) if len(data)>=8 else (-1,-1)
        # Observed in uploaded samples; unknown meaning of the last 128 bytes.
        expected=8+32*count+128 if count>=0 else -1
        valid=version == 1 and len(data) == expected
        entries.append({'file':str(path),'version':version,'record_count':count,
                        'bytes':len(data),'record_width':32,
                        'trailing_bytes':128 if valid else None,
                        'structurally_valid':valid,
                        'trainable':False,
                        'reason':'TAS control semantics and starting state not yet verified'})
    return {'count':len(paths),'structurally_valid':sum(x['structurally_valid'] for x in entries),
            'total_records':sum(x['record_count'] for x in entries if x['structurally_valid']),
            'zero_record_files':sum(x['record_count']==0 for x in entries), 'files':entries}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--duels',type=Path,default=Path('data/replays/ranked-duels'))
    p.add_argument('--doubles',type=Path,default=Path('data/replays/ranked-doubles'))
    p.add_argument('--tas',type=Path,default=Path('data/tas'))
    p.add_argument('--output',type=Path,default=Path('data/source_audit.json'))
    a=p.parse_args()
    audit={'ranked_duels':audit_replays(a.duels),
           'ranked_doubles':audit_replays(a.doubles),
           'tas':audit_tas(a.tas)}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf8')
    for name,v in audit.items():
        print(f'{name}: {v["count"]} files; '+ (f'{v["duplicate_files"]} duplicates' if name!='tas' else f'{v["structurally_valid"]} layouts validated, 0 trainable yet'))
    print('Wrote',a.output)

if __name__=='__main__': main()

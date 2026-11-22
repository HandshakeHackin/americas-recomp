"""Static import lister for PE files: normal imports, delay-load imports, exports. usage: pe_imports.py <dir> <out.json>"""
import json, os, struct, sys

def parse(path):
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    if d[pe:pe+4] != b'PE\0\0':
        return None
    nsec, osz = struct.unpack_from('<H', d, pe + 6)[0], struct.unpack_from('<H', d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    plus = magic == 0x20b
    headers = struct.unpack_from('<I', d, opt + 60)[0]
    dd = opt + (112 if plus else 96)
    ndd = struct.unpack_from('<I', d, dd - 4)[0]
    secs = []
    s = opt + osz
    for i in range(nsec):
        n, vs, va, rs, ro = struct.unpack_from('<8sIIII', d, s + 40 * i)
        secs.append((va, vs, ro, rs))
    def rva(r):
        if 0 <= r < min(headers, len(d)):
            return r
        for va, vs, ro, rs in secs:
            if va <= r < va + max(vs, rs):
                return r - va + ro
        return None
    def cs(o):
        return d[o:d.index(b'\0', o)].decode('latin1')
    def thunks(r, ptr=8 if plus else 4):
        t = rva(r); out = []
        while t is not None:
            v = int.from_bytes(d[t:t+ptr], 'little')
            if not v: break
            if v >> (ptr * 8 - 1): out.append('#%d' % (v & 0xffff))
            else: out.append(cs(rva(v & 0x7fffffff) + 2))
            t += ptr
        return out
    res = {'machine': hex(struct.unpack_from('<H', d, pe + 4)[0]), 'imports': {}, 'delay': {}, 'exports': []}
    def dir_(i):
        return struct.unpack_from('<II', d, dd + 8 * i) if i < ndd else (0, 0)
    er, _ = dir_(0)
    if er:
        o = rva(er)
        base, nf, nn, address_rva, names_rva = struct.unpack_from('<IIIII', d, o + 16)
        addresses, names = rva(address_rva), rva(names_rva)
        res['exports'] = [cs(rva(struct.unpack_from('<I', d, names + 4 * i)[0])) for i in range(nn)]
        res['exports'].extend('#%d' % (base + i) for i in range(nf)
                              if struct.unpack_from('<I', d, addresses + 4 * i)[0])
    ir, _ = dir_(1)
    if ir:
        o = rva(ir)
        while True:
            ol, _, _, nm, ft = struct.unpack_from('<IIIII', d, o)
            if not nm: break
            res['imports'].setdefault(cs(rva(nm)).lower(), []).extend(thunks(ol or ft)); o += 20
    dr, _ = dir_(13)
    if dr:
        o = rva(dr)
        while True:
            attrs, nm, mod, iat, int_, *_ = struct.unpack_from('<IIIIIIII', d, o)
            if not nm: break
            base = 0 if attrs & 1 else None   # RVA-based descriptors only
            res['delay'].setdefault(cs(rva(nm)).lower(), []).extend(thunks(int_)); o += 32
    return res

if __name__ == '__main__':
    out = {}
    for root, _, files in os.walk(sys.argv[1]):
        for f in files:
            if f.lower().endswith(('.dll', '.exe')):
                p = os.path.join(root, f)
                try:
                    r = parse(p)
                except Exception as e:
                    r = {'error': str(e)}
                if r: out[os.path.relpath(p, sys.argv[1])] = r
    json.dump(out, open(sys.argv[2], 'w'), indent=1)
    print(len(out), 'files')


from __future__ import absolute_import
import glob, os, struct

from bup import _helpers
from bup.helpers import log, mmap_read


MIDX_VERSION = 4

extract_bits = _helpers.extract_bits
_total_searches = 0
_total_steps = 0


class MMapMidxReader:
    def __init__(self, filename):
        self.name = filename
        self.map = None
        self.map = mmap_read(open(filename))

    def close(self):
        if self.map is not None:
            self.map.close()
            self.map = None

    def __del__(self):
        self.close()

    def len(self):
        return len(self.map)

    def buffer(self, offset, count):
        return buffer(self.map, offset, count)

class FileMidxReader:
    def __init__(self, filename):
        self.name = filename
        self.f = None
        self.f = open(filename, "rb")

    def close(self):
        if self.f is not None:
            self.f.close()
            self.f = None

    def __del__(self):
        self.close()

    def len(self):
        return os.stat(self.name).st_size

    def buffer(self, offset, count):
        self.f.seek(offset)
        return self.f.read(count)


class PackMidx:
    """Wrapper which contains data from multiple index files.
    Multiple index (.midx) files constitute a wrapper around index (.idx) files
    and make it possible for bup to expand Git's indexing capabilities to vast
    amounts of files.
    """
    def __init__(self, filename, use_mmap=True):
        self.name = filename
        self.force_keep = False
        assert(filename.endswith('.midx'))
        if use_mmap:
            reader = MMapMidxReader(filename)
        else:
            reader = FileMidxReader(filename)
        self.reader = reader
        header = bytes(reader.buffer(0, 4))
        if header != b'MIDX':
            log('Warning: skipping: invalid MIDX header in %r\n' % filename)
            self.force_keep = True
            return self._init_failed()
        ver = struct.unpack('!I', bytes(reader.buffer(4, 4)))[0]
        if ver < MIDX_VERSION:
            log('Warning: ignoring old-style (v%d) midx %r\n' 
                % (ver, filename))
            self.force_keep = False  # old stuff is boring  
            return self._init_failed()
        if ver > MIDX_VERSION:
            log('Warning: ignoring too-new (v%d) midx %r\n'
                % (ver, filename))
            self.force_keep = True  # new stuff is exciting
            return self._init_failed()
        self.bits = _helpers.firstword(reader.buffer(8, 4))
        self.entries = 2**self.bits
        self.sha_ofs = 12 + self.entries*4
        self.nsha = nsha = self._fanget(self.entries-1)
        self.which_ofs = self.sha_ofs + 20*nsha
        idxn_ofs = self.which_ofs + 4 * nsha
        idxn_len = reader.len() - idxn_ofs
        self.idxnames = bytes(reader.buffer(idxn_ofs, idxn_len)).split('\0')

    def __del__(self):
        self.close()

    def _init_failed(self):
        self.bits = 0
        self.entries = 1
        self.idxnames = []

    def _fanget(self, i):
        ## assuming buffer is bufer(offset, count)
        ## fanout offset: 12
        ofs = 12 + i * 4
        ## FIXME: throw
        assert ofs + 4 <= (12 + self.entries * 4)
        return _helpers.firstword(self.reader.buffer(ofs, 4))

    def _get(self, i):
        ofs = self.sha_ofs + i * 20
        ## FIXME: throw
        assert ofs + 20 <= (self.sha_ofs + self.nsha * 20)
        return bytes(self.reader.buffer(ofs, 20))

    def _get_idx_i(self, i):
        ofs = self.which_ofs + i * 4
        ## FIXME: throw?
        assert ofs + 4 <= (self.which_ofs + self.nsha * 4)
        return struct.unpack('!I', self.reader.buffer(ofs, 4))[0]

    def _get_idxname(self, i):
        return self.idxnames[self._get_idx_i(i)]

    def close(self):
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in the index files."""
        global _total_searches, _total_steps
        _total_searches += 1
        want = str(hash)
        el = extract_bits(want, self.bits)
        if el:
            start = self._fanget(el-1)
            startv = el << (32-self.bits)
        else:
            start = 0
            startv = 0
        end = self._fanget(el)
        endv = (el+1) << (32-self.bits)
        _total_steps += 1   # lookup table is a step
        hashv = _helpers.firstword(hash)
        #print '(%08x) %08x %08x %08x' % (extract_bits(want, 32), startv, hashv, endv)
        while start < end:
            _total_steps += 1
            #print '! %08x %08x %08x   %d - %d' % (startv, hashv, endv, start, end)
            mid = start + (hashv-startv)*(end-start-1)/(endv-startv)
            #print '  %08x %08x %08x   %d %d %d' % (startv, hashv, endv, start, mid, end)
            v = self._get(mid)
            #print '    %08x' % self._num(v)
            if v < want:
                start = mid+1
                startv = _helpers.firstword(v)
            elif v > want:
                end = mid
                endv = _helpers.firstword(v)
            else: # got it!
                return want_source and self._get_idxname(mid) or True
        return None

    def iter_with_idx_i(self, ofs):
        for i in xrange(self._fanget(self.entries-1)):
            table_ofs = self.sha_ofs + i * 20
            # FIXME: throw
            #assert (table_ofs + 20) < shatable_end
            yield self.reader.buffer(table_ofs, 20), ofs + self._get_idx_i(i)

    def __iter__(self):
        shatable_end = self.sha_ofs + self.nsha * 20
        for i in xrange(self._fanget(self.entries-1)):
            ofs = self.sha_ofs + i * 20
            # FIXME: throw
            #assert (ofs + 20) < shatable_end
            yield self.reader.buffer(ofs, 20)

    def __len__(self):
        return int(self._fanget(self.entries-1))


def clear_midxes(dir=None):
    for midx in glob.glob(os.path.join(dir, '*.midx')):
        os.unlink(midx)

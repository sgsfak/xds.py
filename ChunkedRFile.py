CRLF = '\r\n'
class MaxSizeExceeded(Exception):
    pass
class ChunkedRFile(object):
    """Wraps a file-like object, returning an empty string when exhausted.
    
    This class is intended to provide a conforming wsgi.input value for
    request entities that have been encoded with the 'chunked' transfer
    encoding.
    """
    
    def __init__(self, rfile, maxlen, bufsize=8192):
        self.rfile = rfile
        self.maxlen = maxlen
        self.bytes_read = 0
        self.buffer = ''
        self.bufsize = bufsize
        self.closed = False
    
    def _fetch(self):
        if self.closed:
            return
        
        line = self.rfile.readline()
        # print "READ >%s<" % line
        self.bytes_read += len(line)
        
        if self.maxlen and self.bytes_read > self.maxlen:
            raise MaxSizeExceeded("Request Entity Too Large", self.maxlen)
        
        line = line.strip().split(";", 1)
        
        try:
            chunk_size = line.pop(0)
            chunk_size = int(chunk_size, 16)
        except ValueError:
            raise ValueError("Bad chunked transfer size: " + repr(chunk_size))
        
        if chunk_size <= 0:
            self.closed = True
            return
        
##            if line: chunk_extension = line[0]
        
        if self.maxlen and self.bytes_read + chunk_size > self.maxlen:
            raise IOError("Request Entity Too Large")
        
        chunk = self.rfile.read(chunk_size)
        self.bytes_read += len(chunk)
        self.buffer += chunk
        
        crlf = self.rfile.read(2)
        if crlf != CRLF:
            raise ValueError(
                 "Bad chunked transfer coding (expected '\\r\\n', "
                 "got " + repr(crlf) + ")")
    
    def read(self, size=None):
        data = ''
        while True:
            if size and len(data) >= size:
                return data
            
            if not self.buffer:
                self._fetch()
                if not self.buffer:
                    # EOF
                    return data
            
            if size:
                remaining = size - len(data)
                data += self.buffer[:remaining]
                self.buffer = self.buffer[remaining:]
            else:
                data += self.buffer
    
    def readline(self, size=None):
        data = ''
        while True:
            if size and len(data) >= size:
                return data
            
            if not self.buffer:
                self._fetch()
                if not self.buffer:
                    # EOF
                    return data
            
            newline_pos = self.buffer.find('\n')
            if size:
                if newline_pos == -1:
                    remaining = size - len(data)
                    data += self.buffer[:remaining]
                    self.buffer = self.buffer[remaining:]
                else:
                    remaining = min(size - len(data), newline_pos)
                    data += self.buffer[:remaining]
                    self.buffer = self.buffer[remaining:]
            else:
                if newline_pos == -1:
                    data += self.buffer
                else:
                    data += self.buffer[:newline_pos]
                    self.buffer = self.buffer[newline_pos:]
    
    def readlines(self, sizehint=0):
        # Shamelessly stolen from StringIO
        total = 0
        lines = []
        line = self.readline(sizehint)
        while line:
            lines.append(line)
            total += len(line)
            if 0 < sizehint <= total:
                break
            line = self.readline(sizehint)
        return lines
    
    def read_trailer_lines(self):
        if not self.closed:
            raise ValueError(
                "Cannot read trailers until the request body has been read.")
        
        while True:
            line = self.rfile.readline()
            if not line:
                # No more data--illegal end of headers
                raise ValueError("Illegal end of headers.")
            
            self.bytes_read += len(line)
            if self.maxlen and self.bytes_read > self.maxlen:
                raise IOError("Request Entity Too Large")
            
            if line == CRLF:
                # Normal end of headers
                break
            if not line.endswith(CRLF):
                raise ValueError("HTTP requires CRLF terminators")
            
            yield line
    
    def close(self):
        self.rfile.close()
    
    def __iter__(self):
        # Shamelessly stolen from StringIO
        total = 0
        line = self.readline(sizehint)
        while line:
            yield line
            total += len(line)
            if 0 < sizehint <= total:
                break
            line = self.readline(sizehint)

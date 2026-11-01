"""Read exception/module/stack metadata from the local game's Windows minidump."""
import json
import mmap
import struct
import sys

with open(sys.argv[1], 'rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as blob:
    def read(fmt, offset):
        return struct.unpack_from('<' + fmt, blob, offset)
    count, directory = read('II', 8)
    streams = {kind: (size, rva) for kind, size, rva in (read('III', directory + i*12) for i in range(count))}
    modules = []
    _, loc = streams[4]
    for i in range(read('I', loc)[0]):
        base, size, _, _, name = read('QIIII', loc+4+i*108)
        length = read('I', name)[0]
        modules.append((base, size, blob[name+4:name+4+length].decode('utf-16-le')))
    def describe(address):
        for base, size, name in modules:
            if base <= address < base + size:
                return name.split('\\')[-1] + '+' + hex(address-base)
        return 'unmapped:' + hex(address)
    ranges = []
    if 5 in streams:
        _, loc = streams[5]
        for i in range(read('I', loc)[0]):
            address, size, offset = read('QII', loc+4+i*16)
            ranges.append((address, size, offset))
    if 9 in streams:
        _, loc = streams[9]
        n, offset = read('QQ', loc)
        for i in range(n):
            address, size = read('QQ', loc+16+i*16)
            ranges.append((address, size, offset))
            offset += size
    def memory(address, length):
        for start, size, offset in ranges:
            if start <= address and address + length <= start + size:
                return blob[offset+address-start:offset+address-start+length]
        return b''
    _, loc = streams[6]
    thread = read('I', loc)[0]
    code = read('I', loc+8)[0]
    address = read('Q', loc+24)[0]
    n = read('I', loc+32)[0]
    params = read('Q'*min(n, 15), loc+40)
    ctx_size, ctx = read('II', loc+160)
    registers = {name: read('Q', ctx+offset)[0] for name,offset in [('rax',120),('rcx',128),('rdx',136),('rbx',144),('rsp',152),('rbp',160),('rsi',168),('rdi',176),('rip',248)]}
    stack = memory(registers['rsp'], 1024)
    rows = []
    for i in range(len(stack)//8):
        value = struct.unpack_from('<Q', stack, i*8)[0]
        label = describe(value)
        if not label.startswith('unmapped:'):
            rows.append({'offset':hex(i*8),'address':hex(value),'module':label})
    print(json.dumps({'streams':list(streams),'thread':thread,'exception':hex(code),'address':describe(address),'parameters':[hex(x) for x in params],
        'registers':{k:hex(v) for k,v in registers.items()},'stack_module_addresses':rows,'fault_bytes':memory(address,32).hex(),
        'game_modules':[(hex(base),size,name) for base,size,name in modules if any(s in name.lower() for s in ('frida','gamedll','engine_x64','dyinglight'))]},indent=2))

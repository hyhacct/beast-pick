import sys
from pathlib import Path
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

path=Path(r'D:\App\Steam\steamapps\common\Dying Light The Beast\ph_ft\work\bin\x64\gamedll_ph_x64_rwdi.dll')
pe=pefile.PE(str(path),fast_load=True)
md=Cs(CS_ARCH_X86,CS_MODE_64)
for arg in sys.argv[1:]:
    rva=int(arg,16)
    print(f'FUNCTION {rva:x}')
    for ins in md.disasm(pe.get_data(rva,1800),rva):
        print(f'{ins.address:x} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic=='ret':break

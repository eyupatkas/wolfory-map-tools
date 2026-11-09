"""Bounded data-only WAD3 miptex decoding (Valve SDK wadlib/bspfile layouts)."""
import struct
from pathlib import Path
from PIL import Image


def textures(path,names=None):
    data=Path(path).read_bytes()
    if not 12<=len(data)<=48_000_000 or data[:4]!=b'WAD3':raise ValueError('Expected bounded WAD3')
    count,offset=struct.unpack_from('<ii',data,4)
    if not 0<=count<=8192 or not 12<=offset<=len(data)-32*count:raise ValueError('WAD directory bounds')
    result={}
    for i in range(count):
        pos,size,raw,kind,compression,_,name=struct.unpack_from('<iiiBBH16s',data,offset+32*i)
        if kind!=67:continue
        if compression or not 0<=pos<=len(data)-size or not 40<=size<=2_000_000:raise ValueError('WAD miptex bounds')
        name=name.split(b'\0')[0].decode('latin1').lower()
        if names is not None and name not in names:continue
        _,w,h,*mips=struct.unpack_from('<16s6I',data,pos)
        if not 8<=w<=1024 or not 8<=h<=1024 or w%8 or h%8:raise ValueError('WAD texture dimensions')
        if any(not 40<=m<=size-(w>>j)*(h>>j) for j,m in enumerate(mips)):raise ValueError('WAD mip offset')
        palette=mips[3]+(w//8)*(h//8)
        if palette+770>size or struct.unpack_from('<H',data,pos+palette)[0]!=256:raise ValueError('WAD palette bounds')
        colors=data[pos+palette+2:pos+palette+770]
        indices=data[pos+mips[0]:pos+mips[0]+w*h]
        rgba=bytes(c for index in indices for c in (*colors[index*3:index*3+3],0 if name.startswith('{') and index==255 else 255))
        result[name]=Image.frombytes('RGBA',(w,h),rgba)
    return result

(() => {
 const count=p=>p.add(7).readU8()?p.add(7).readU8()-1:p.add(8).readU32();
 const vec=new NativeFunction(gamePtr.readPointer().add(152*8).readPointer(),'pointer',['pointer'])(gamePtr);
 const ent=new NativeFunction(gamePtr.readPointer().add(153*8).readPointer(),'pointer',['pointer'])(gamePtr);
 const ctl=new NativeFunction(exported('?GetControlObject@IControlObject@@SAPEAV1@PEBVCEntity@cbs@@@Z'),'pointer',['pointer'])(ent);
 const vf=gamePtr.readPointer(),matches=[];
 for(let i=0;i<0x4000;i+=8){try{if(gamePtr.add(i).readPointer().equals(levelPtr))matches.push(i);}catch(e){break;}}
 const slots=[84,87,162,164,165,166,167,170,171,172,173,175,176,179,180,181,182,183,184,187,210,230,231,232,233,250,269,270,296,303,313,319,321,322,325,347,348];
 return {players:count(vec),entity:ent.toString(),control:ctl.toString(),playerType:className(ctl),matches,functions:slots.map(i=>{let p=vf.add(i*8).readPointer(),asm=[];try{for(let j=0;j<8;j++){const ins=Instruction.parse(p);asm.push(ins.toString());p=ins.next;if(ins.mnemonic==='ret')break;}}catch(e){}return {i,p:describe(vf.add(i*8).readPointer()),asm};})};
})()

(() => {
  const out = Memory.alloc(16);
  const storage = Memory.alloc(65536);
  const pos = Memory.alloc(12);
  out.writePointer(storage);
  out.add(8).writeU32(0);
  out.add(12).writeU32(8192);
  const mat = new NativeFunction(gamePtr.readPointer().add(151 * 8).readPointer(), 'pointer', ['pointer'])(gamePtr);
  for (let i = 0; i < 3; i++) pos.add(i * 4).writeFloat(mat.add((i * 4 + 3) * 4).readFloat());
  const fn = new NativeFunction(exported('?FindObjectsInRadius@ILevel@@QEAA_NPEAV?$vector@PEAVIControlObject@@V?$heap_allocator@PEAVIControlObject@@@vector_allocators@ttl@@$00@ttl@@AEBVvec3@@MPEBVCRTTI@@_NPEAH@Z'), 'bool', ['pointer', 'pointer', 'pointer', 'float', 'pointer', 'bool', 'pointer']);
  const ok = fn(levelPtr, out, pos, 8.0, ptr(0), 0, ptr(0));
  const packed = out.readU64();
  const sizeCode = out.add(7).readU8();
  const n = sizeCode ? sizeCode - 1 : out.add(8).readU32();
  const data = ptr(packed.and(uint64('0xffffffffffff')).toString());
  globalThis.nearbyObjects = [];
  for (let i = 0; i < Math.min(n, 8192); i++) nearbyObjects.push(data.add(i * 8).readPointer());
  return {ok, n, position: [pos.readFloat(), pos.add(4).readFloat(), pos.add(8).readFloat()], objects: nearbyObjects.map(p => ({ptr: p.toString(), type: className(p)}))};
})()

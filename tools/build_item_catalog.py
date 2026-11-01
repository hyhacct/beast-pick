"""Build a read-only item catalog from this installation's scripts and Chinese names."""
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from beast_pick.categories import ITEM_TYPES
SOURCE=Path(r'D:\App\Steam\steamapps\common\Dying Light The Beast\ph_ft\source')

def localization(blob):
    def array(name):
        offset=blob.index(name)+len(name)+4
        count=struct.unpack_from('<I',blob,offset)[0];offset+=4;result=[]
        for _ in range(count):
            length=struct.unpack_from('<H',blob,offset)[0];offset+=2
            result.append(blob[offset:offset+length].decode('utf-8'));offset+=length
        return result
    keys,values=array(b'm_keys'),array(b'm_Values')
    assert len(keys)==len(values)
    return dict(zip(keys,values))

def resolved_label(key, translations, fallback):
    label=translations.get(key.lower()) or fallback
    # Localized names can themselves reference another localized name.
    for _ in range(16):
        if '&' not in label:
            return label
        updated=re.sub(r'&([^&\r\n]+)&',lambda m:translations.get(m[1].lower(),m[0]),label)
        if updated==label:
            return fallback
        label=updated
    return fallback

def blocks(text):
    # Ignore comments while preserving quoted names and string content.
    text=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/', '', text)
    pattern=re.compile(r'\b(sub\s+(\w+)\s*\([^)]*\)|Item\s*\(\s*"([^"]+)"\s*,\s*(\w+)\s*\))\s*\{')
    for match in pattern.finditer(text):
        start=match.end();depth=1;quoted=False;escaped=False;i=start
        while i<len(text) and depth:
            c=text[i]
            if escaped:escaped=False
            elif c=='\\' and quoted:escaped=True
            elif c=='"':quoted=not quoted
            elif not quoted:
                if c=='{':depth+=1
                elif c=='}':depth-=1
            i+=1
        if depth:raise ValueError('Unbalanced inventory block: '+str(match.group(2)or match.group(3)))
        yield match.group(2),match.group(3),match.group(4),text[start:i-1]

TYPE_NAMES={
    'ThrowingStar':'飞刀 / 飞镖','Grenade':'手雷','Molotov':'燃烧瓶','Flare':'照明弹','Liquid':'投掷液体',
    'Mine':'地雷','C4':'遥控炸药','DiyGrenade':'自制手雷','Firecracker':'鞭炮 / 诱饵','Stick':'棍棒类',
    'Knife':'刀具','Axe':'斧头','BigAxe':'双手斧','Machete':'砍刀','Sword':'长剑','Hammer':'锤子',
    'BigHammer':'双手锤','Pistol':'手枪','Revolver':'左轮手枪','Rifle':'步枪','Shotgun':'霰弹枪',
    'Smg':'冲锋枪','SMG':'冲锋枪','Bow':'弓','Crossbow':'弩','Medkit':'医疗包','MedKit':'医疗包',
    'CraftPart':'制作部件','CraftComponent':'制作材料','Ammo':'弹药','Cash':'现金','Valuable':'贵重物品',
    'Powerup':'食物 / 增益','Fuel':'燃料','Lockpick':'开锁器','OutfitPart':'服装部件',
    'Decoy':'诱饵 / 鞭炮','Flashbang':'闪光弹','ThrowablePrefab':'放置式投掷物','ThrowableKnife':'投掷刀',
    'Explosion':'爆炸物','Fists':'特殊近身物品','Special':'特殊物品','ThrowableLiquid':'投掷液体',
    'ThrowableSpear':'投矛','ThrowableStone':'投石','Injector':'食物 / 注射器','Valuables':'贵重物品',
    'CraftPlan':'制作蓝图','Note':'笔记','Tape':'录音带','TreasureMap':'藏宝图','PostCard':'明信片',
    'PlayerAppearance':'角色外观','PortableCamouflage':'便携伪装','ItemBundle':'物资包',
    'Collision':'碰撞类','Mace':'钉头锤','Halberd':'长柄武器','Knuckles':'指虎','Bullet':'子弹',
    'GrenadeLauncher':'榴弹发射器','FakeStashItem':'存储占位物品','QuestItem':'任务物品','Token':'代币',
    'VirtualItem':'虚拟物品','SawbladeLauncher':'锯片发射器','FlameThrower':'喷火器','SubMachineGun':'冲锋枪',
    'Other':'其他','Melee':'近战武器','Binoculars':'望远镜','FreeClimb':'徒手攀爬','Hook':'抓钩',
    'Flashlight':'手电筒','StaminaBooster':'耐力增强剂','Key':'钥匙','SummoningTool':'召唤工具',
    'Collectible_FuryPoint':'狂怒点数','Docket':'兑换券','LootPack':'战利品包','VehicleSkin':'载具涂装',
}

def main():
    with zipfile.ZipFile(SOURCE/'data_lang/datacn.pak')as z:
        loc=localization(z.read('texts/pc/pc_cn_lang.binsloc'))
    loc_lower={k.lower():v for k,v in loc.items()}
    macros={};items={};texts={}
    with zipfile.ZipFile(SOURCE/'data0.pak')as z:
        for name in z.namelist():
            if name.startswith('scripts/inventory/') and name.endswith('.scr') and '/'not in name.removeprefix('scripts/inventory/'):
                text=z.read(name).decode('utf-8-sig',errors='replace');texts[name]=text
                for macro,item,category,body in blocks(text):
                    if macro:macros[macro]=body
                    else:
                        # The game repeats an Item declaration to patch only
                        # selected fields (e.g. firearm aiming behavior). Keep
                        # previous Name/ItemType until an explicit override.
                        previous=items.get(item)
                        items[item]=(category,(previous[1]+'\n' if previous else '')+body)
    enum={name:int(number)for name,number in re.findall(r'CategoryType_(\w+)\s*=\s*(-?\d+)',texts['scripts/inventory/inventorystuff.scr'])}
    token=re.compile(r'\buse\s+(\w+)\s*\([^;]*\)\s*;|\b(Name|ItemType|WpnSubtype)\s*\(\s*("[^"]*"|\w+)\s*\)')
    def fields(body,seen=()):
        result={}
        for match in token.finditer(body):
            macro,key,value=match.groups()
            if macro and macro in macros and macro not in seen and len(seen)<16:
                result.update(fields(macros[macro],(*seen,macro)))
            elif key:result[key]=value.strip('"')
        return result
    catalog={};subtypes={}
    for identity,(category,body)in items.items():
        number=enum.get(category.removeprefix('CategoryType_'))
        group=next((key for key,(_,ids)in ITEM_TYPES.items()if number in ids),None)
        if group is None:continue
        attrs=fields(body);namekey=attrs.get('Name','').strip('&')or identity+'_n'
        label=resolved_label(namekey,loc_lower,identity)
        type_name=attrs.get('WpnSubtype')if group=='weapons' else None
        type_name=type_name or attrs.get('ItemType')or category
        suffix=re.sub(r'^(EWpnSubtype_|ItemType_|CategoryType_)','',type_name)
        subtype=group+':'+type_name
        subtypes[subtype]={'name':TYPE_NAMES.get(suffix,suffix),'group':group,'symbol':type_name}
        catalog[identity]={'name':label,'group':group,'category':number,'subtype':subtype}
    output={'version':1,'items':catalog,'subtypes':subtypes,'source_sha256':{
        'data0.pak':hashlib.file_digest((SOURCE/'data0.pak').open('rb'),'sha256').hexdigest(),
        'datacn.pak':hashlib.file_digest((SOURCE/'data_lang/datacn.pak').open('rb'),'sha256').hexdigest()}}
    target=ROOT/'beast_pick/data/items.json';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'items':len(catalog),'subtypes':subtypes,'throwable_sample':{k:v for k,v in catalog.items()if v['group']=='throwables'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

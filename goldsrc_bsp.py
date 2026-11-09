"""Bounded read-only GoldSrc BSP30 geometry reader, per Valve SDK bspfile.h.

Data only: does not load game libraries, run entities, download or install maps.
"""
from pathlib import Path
import collections
import hashlib
import json
import math
import re
import struct


class BSP30:
    def __init__(self,path):
        self.data=Path(path).read_bytes()
        if not 124<len(self.data)<=8_000_000 or struct.unpack_from('<i',self.data)[0]!=30:raise ValueError('Expected bounded GoldSrc BSP30')
        self.sha256=hashlib.sha256(self.data).hexdigest()
        self.lumps=[struct.unpack_from('<ii',self.data,4+i*8) for i in range(15)]
        if not all(124<=a<=len(self.data) and 0<=n<=len(self.data)-a for a,n in self.lumps):raise ValueError('BSP lump overrun')
        def array(index,fmt,limit):
            a,n=self.lumps[index];size=struct.calcsize(fmt)
            if n%size or n//size>limit:raise ValueError('BSP array bounds')
            return list(struct.iter_unpack(fmt,self.data[a:a+n]))
        self.planes=array(1,'<4fi',32767);self.vertices=array(3,'<3f',65535)
        self.nodes=array(5,'<i2h6h2H',32767);self.texinfo=array(6,'<8f2i',8192)
        self.faces=array(7,'<2hi2h4Bi',65535);self.leaves=array(10,'<2i6h2H4B',8192)
        self.edges=array(12,'<2H',256000);self.surfedges=[x[0] for x in array(13,'<i',512000)]
        self.models=array(14,'<9f7i',400)
        a,n=self.lumps[0]
        if n>128*1024:raise ValueError('Entity text exceeds bound')
        text=self.data[a:a+n].rstrip(b'\0').decode('latin1')
        self.entities=[dict(re.findall(r'"([^"\r\n]{1,128})"\s*"([^"\r\n]{0,2048})"',block)) for block in re.findall(r'\{([^{}]*)\}',text)]
        if len(self.entities)>1024:raise ValueError('Entity count')
        self.model_entities={int(e['model'][1:]):e for e in self.entities if re.fullmatch(r'\*\d+',e.get('model',''))}
        a,n=self.lumps[2];count=struct.unpack_from('<i',self.data,a)[0]
        if not 0<count<=512 or 4+count*4>n:raise ValueError('Texture directory')
        self.textures=[]
        for i in range(count):
            p=struct.unpack_from('<i',self.data,a+4+i*4)[0]
            if p==-1:self.textures.append({'name':'missing','dimensions':[0,0]});continue
            if not 0<=p<=n-40:raise ValueError('Texture offset')
            name,w,h,*offsets=struct.unpack_from('<16s6I',self.data,a+p)
            name=name.split(b'\0')[0].decode('latin1')
            self.textures.append({'name':name,'dimensions':[w,h],'embedded':bool(offsets[0])})
        for node in self.nodes:
            if not 0<=node[0]<len(self.planes):raise ValueError('Invalid node plane')
            if any(c>=len(self.nodes) or c<0 and -c-1>=len(self.leaves) for c in node[1:3]):raise ValueError('Invalid node child')
        self.face_models={}
        for i,m in enumerate(self.models):
            first,count=m[-2:]
            if not 0<=first<=len(self.faces) or not 0<=count<=len(self.faces)-first:raise ValueError('Invalid model face range')
            for f in range(first,first+count):self.face_models[f]=i

    def polygon(self,index):
        plane,side,first,n,texture,*_=self.faces[index]
        if not 0<=plane<len(self.planes) or not 0<=texture<len(self.texinfo) or not 3<=n<=256 or not 0<=first<=len(self.surfedges)-n:raise ValueError('Face references invalid')
        vertices=[]
        for edge in self.surfedges[first:first+n]:
            if not 0<=abs(edge)<len(self.edges):raise ValueError('Edge reference invalid')
            i=self.edges[abs(edge)][0 if edge>=0 else 1]
            if not 0<=i<len(self.vertices):raise ValueError('Vertex reference invalid')
            vertices.append(self.vertices[i])
        info=self.texinfo[texture];tex=info[-2]
        if not 0<=tex<len(self.textures):raise ValueError('Texture reference invalid')
        normal=list(self.planes[plane][:3]);distance=self.planes[plane][3]
        if side:normal=[-x for x in normal];distance=-distance
        return {'id':index,'model':self.face_models.get(index,0),'vertices':vertices,'normal':normal,'distance':distance,
                'texture':self.textures[tex]['name'],'textureInfo':info[:8],'textureDimensions':self.textures[tex]['dimensions']}

    def summary(self):
        spawns=[e for e in self.entities if e.get('classname') in ('info_player_start','info_player_deathmatch')]
        objects=[]
        for i,e in self.model_entities.items():
            m=self.models[i];objects.append({'model':i,'class':e.get('classname'),'name':e.get('targetname'),
                'bounds':[m[:3],m[3:6]],'faces':m[-1], 'angle':e.get('angle'),'angles':e.get('angles'),'flags':e.get('spawnflags')})
        return {'sha256':self.sha256,'world':self.entities[0],
                'counts':{'models':len(self.models),'faces':len(self.faces),'nodes':len(self.nodes),'leaves':len(self.leaves)},
                'classes':dict(collections.Counter(e.get('classname') for e in self.entities)),'worldBounds':[self.models[0][:3],self.models[0][3:6]],
                'spawns':spawns,'modelEntities':objects,'textures':self.textures}

    def solid_cells(self,model_index=0):
        """Recover bounded convex solid/sky cells from the original hull0 BSP.

        Internal BSP cuts are retained; no missing brushes are guessed from a
        surface extrusion. These cells describe actual solid space in this BSP.
        """
        model=self.models[model_index];lo,hi=model[:3],model[3:6]
        x,y,z=lo;X,Y,Z=hi
        p=[(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)]
        quads=[[0,3,2,1],[4,5,6,7],[0,4,7,3],[1,2,6,5],[0,1,5,4],[3,7,6,2]]
        faces=[{'vertices':[p[i] for i in ids],'plane':None} for ids in quads]
        result=[];visits=0
        def clipped(faces,normal,distance,plane):
            allpoints=[p for f in faces for p in f['vertices']]
            dots=[sum(a*b for a,b in zip(normal,p))-distance for p in allpoints]
            if max(dots)<.00001:return faces
            if min(dots)>-.00001:return None
            output=[];cuts=[]
            for face in faces:
                poly=face['vertices'];new=[]
                for a,b in zip(poly,poly[1:]+poly[:1]):
                    da=sum(n*v for n,v in zip(normal,a))-distance;db=sum(n*v for n,v in zip(normal,b))-distance
                    if da<=.000001:new.append(a)
                    if (da<-.000001 and db>.000001) or (da>.000001 and db<-.000001):
                        t=da/(da-db);q=tuple(a[j]+t*(b[j]-a[j]) for j in range(3));new.append(q);cuts.append(q)
                    elif abs(da)<=.000001:cuts.append(a)
                clean=[]
                for v in new:
                    if not clean or max(abs(a-b) for a,b in zip(v,clean[-1]))>.00001:clean.append(v)
                if len(clean)>1 and max(abs(a-b) for a,b in zip(clean[0],clean[-1]))<.00001:clean.pop()
                if len(clean)>=3:output.append({**face,'vertices':clean})
            unique=[]
            for q in cuts:
                if not any(max(abs(a-b) for a,b in zip(q,v))<.00001 for v in unique):unique.append(q)
            if len(unique)<3:return None
            center=[sum(p[j] for p in unique)/len(unique) for j in range(3)]
            reference=(1,0,0) if abs(normal[0])<.9 else (0,1,0)
            cross=lambda a,b:(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
            u=cross(reference,normal);length=math.sqrt(sum(v*v for v in u));u=tuple(v/length for v in u);v=cross(normal,u)
            unique.sort(key=lambda p:math.atan2(sum((p[j]-center[j])*v[j] for j in range(3)),sum((p[j]-center[j])*u[j] for j in range(3))))
            output.append({'vertices':unique,'plane':plane})
            return output
        def walk(index,faces,depth):
            nonlocal visits
            visits+=1
            if visits>20000 or depth>256:raise ValueError('BSP traversal budget/cycle')
            if index<0:
                contents=self.leaves[-index-1][0]
                if contents in (-2,-6):result.append({'model':model_index,'contents':contents,'faces':faces})
                return
            node=self.nodes[index];n=self.planes[node[0]][:3];d=self.planes[node[0]][3]
            for side,child in enumerate(node[1:3]):
                normal=n if side else tuple(-x for x in n);distance=d if side else -d
                next_faces=clipped(faces,normal,distance,(node[0],side))
                if next_faces:walk(child,next_faces,depth+1)
        root=model[9]
        if not 0<=root<len(self.nodes):raise ValueError('Model hull0 root')
        walk(root,faces,0)
        return result


if __name__=='__main__':
    import sys
    bsp=BSP30(sys.argv[1]);target=Path(sys.argv[2]);target.write_text(json.dumps(bsp.summary(),indent=2)+'\n')
    print(json.dumps({k:bsp.summary()[k] for k in ('sha256','counts','classes','worldBounds')}))

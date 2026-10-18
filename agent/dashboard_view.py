"""Read-only game-style map and inventory; never dispatches gameplay."""
import math
import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from factorio_theme import PANEL, INSET, TEXT

RESOURCE_COLORS = {'iron-ore':'#7699bf','copper-ore':'#cf743c','coal':'#26292c','stone':'#bdb28b','uranium-ore':'#79b627','crude-oil':'#be41bd'}
QUALITY_COLORS = {'normal':'#bbb9ae','uncommon':'#68b64b','rare':'#529bea','epic':'#ae61d5','legendary':'#e6a135'}


def project(position, center, width, height, radius):
    scale = min(width, height) / (2 * radius)
    return width/2 + (position['x']-center['x'])*scale, height/2 + (position['y']-center['y'])*scale


def terrain_color(name):
    if 'water' in name or 'ocean' in name: return '#285d78'
    if 'lava' in name: return '#a54b22'
    if 'grass' in name: return '#59653b'
    if 'sand' in name: return '#a79768'
    if 'snow' in name or 'ice' in name: return '#9facb4'
    if 'concrete' in name or 'stone-path' in name: return '#777b76'
    if 'out-of-map' in name: return '#111416'
    return '#78694e'


def raster_pixels(terrain,center,width,height,radius):
    """Nearest-tile projection; no repeated oversized cell rectangles when zoomed out."""
    scale=min(width,height)/(2*radius)
    ox,oy=terrain['origin']['x'],terrain['origin']['y']
    palette=[bytes.fromhex(c[1:]) for c in terrain['palette']]
    rows=[bytes.fromhex(row) for row in terrain['rows']]
    xs=[math.floor(center['x']+(x-width/2)/scale)-int(ox) for x in range(width)]
    output=[];cache={}
    for y in range(height):
        iy=math.floor(center['y']+(y-height/2)/scale)-int(oy)
        if iy not in cache:
            cache[iy]=(b''.join(palette[rows[iy][x]] if 0<=x<256 else b'\0\0\0' for x in xs)
                       if 0<=iy<256 else b'\0\0\0'*width)
        output.append(cache[iy])
    return b''.join(output)


class LiveView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.last=None; self.received=None; self.available=False
        self.offset={'x':0,'y':0}; self.drag=None; self.icons={}; self.slot_hits=[]
        self.status=tk.StringVar(value='Connecting live observer (AI can remain stopped)')
        self.zoom=tk.StringVar(value='128')
        ttk.Label(self,textvariable=self.status,style='Muted.TLabel').pack(anchor='w',padx=8,pady=4)
        controls=ttk.Frame(self); controls.pack(fill='x',padx=8)
        ttk.Label(controls,text='Radius:').pack(side='left')
        zoom=ttk.Combobox(controls,textvariable=self.zoom,values=['24','60','128','200'],state='readonly',width=5)
        zoom.pack(side='left',padx=6); zoom.bind('<<ComboboxSelected>>',lambda _:self.draw())
        ttk.Button(controls,text='Follow player',command=self.recenter).pack(side='left')
        ttk.Button(controls,text='−',width=3,command=lambda:self.change_zoom(1.25)).pack(side='left',padx=2)
        ttk.Button(controls,text='+',width=3,command=lambda:self.change_zoom(.8)).pack(side='left',padx=2)
        self.pointer=tk.StringVar(value='Drag to pan · Wheel to zoom · North up')
        ttk.Label(controls,textvariable=self.pointer,style='Muted.TLabel').pack(side='left',padx=8)
        layers=ttk.Menubutton(controls,text='Map layers ▾');layers.pack(side='right')
        menu=tk.Menu(layers,tearoff=False);layers.configure(menu=menu)
        self.layers={}
        for key,label in [('resource','Resources'),('nature','Trees and rocks'),('building','Buildings'),('enemy','Enemies'),('history','Visited areas and failed targets'),('goals','Objective and proposed route'),('grid','Chunk grid'),('player_name','Player marker label')]:
            self.layers[key]=tk.BooleanVar(value=key!='grid')
            menu.add_checkbutton(label=label,variable=self.layers[key],command=self.draw)
        menu.add_separator()
        self.overlay_menu=menu;self.overlay_entries={}
        for key,label in [('pollution','Pollution'),('electric','Electric supply and connections'),('logistics','Logistics and construction coverage'),('turrets','Turret nominal range'),('stations','Train stop names'),('tags','Map tags')]:
            self.layers[key]=tk.BooleanVar(value=False)
            menu.add_checkbutton(label=label+' — unavailable',variable=self.layers[key],command=self.draw,state='disabled')
            self.overlay_entries[key]=(menu.index('end'),label)
        ttk.Label(self,text='Local chart window · Visible entities only · Turret circles show nominal range, not combat readiness.',style='Muted.TLabel').pack(anchor='w',padx=8,pady=2)
        body=ttk.Panedwindow(self,orient='horizontal'); body.pack(fill='both',expand=True,padx=8,pady=6)
        map_frame=ttk.Frame(body); body.add(map_frame,weight=3)
        self.canvas=tk.Canvas(map_frame,background='#111416',highlightthickness=0,width=660,height=310)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda _:self.draw())
        self.canvas.bind('<ButtonPress-1>',self.pan_start)
        self.canvas.bind('<B1-Motion>',self.pan_move)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Motion>',self.map_pointer)
        self.canvas.bind('<Double-Button-1>',lambda _:self.recenter())
        inventory=ttk.Frame(body,width=425,padding=(8,4)); body.add(inventory,weight=1)
        self.inventory_status=tk.StringVar(value='Player main inventory: waiting')
        ttk.Label(inventory,textvariable=self.inventory_status,style='Section.TLabel').pack(anchor='w')
        self.item_hint=tk.StringVar(value='Hover a slot for item and quality · Read-only')
        ttk.Label(inventory,textvariable=self.item_hint,wraplength=400,style='Muted.TLabel').pack(anchor='w',pady=4)
        self.items=tk.Canvas(inventory,background=INSET,highlightthickness=0,width=410)
        self.items.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(inventory,orient='vertical',command=self.items.yview)
        scroll.pack(side='right',fill='y');self.items.configure(yscrollcommand=scroll.set)
        self.items.bind('<Motion>',self.hover)
        self.items.bind('<MouseWheel>',lambda e:self.items.yview_scroll(-1 if e.delta>0 else 1,'units'))
        self.icon_root=Path(os.environ.get('AUTOENGINEER_FACTORIO_DATA',r'C:/Program Files (x86)/Steam/steamapps/common/Factorio/data'))

    def recenter(self):
        self.offset={'x':0,'y':0};self.draw()

    def pan_start(self,e):
        self.drag=(e.x,e.y,dict(self.offset))

    def pan_move(self,e):
        if self.drag is None:return
        x,y,old=self.drag
        scale=min(self.canvas.winfo_width(),self.canvas.winfo_height())/(2*float(self.zoom.get()))
        self.offset={k:max(-128,min(128,old[k]-delta/scale)) for k,delta in [('x',e.x-x),('y',e.y-y)]}
        self.draw()

    def change_zoom(self,factor):
        self.zoom.set(str(max(8,min(200,round(float(self.zoom.get())*factor,1)))))
        self.draw()

    def wheel(self,e):
        self.change_zoom(.8 if e.delta>0 else 1.25)

    def map_pointer(self,e):
        if self.last is None:return
        scale=min(self.canvas.winfo_width(),self.canvas.winfo_height())/(2*float(self.zoom.get()))
        if scale<=0:return
        player=self.last['position']
        x=player['x']+self.offset['x']+(e.x-self.canvas.winfo_width()/2)/scale
        y=player['y']+self.offset['y']+(e.y-self.canvas.winfo_height()/2)/scale
        self.pointer.set(f'Cursor {x:.1f}, {y:.1f} · Drag to pan · Double-click to follow')

    def reset(self):
        self.last=None;self.received=None;self.available=False;self.offset={'x':0,'y':0}
        self.status.set('Waiting for live data');self.inventory_status.set('Player main inventory: waiting')
        self.items.delete('all');self.slot_hits=[];self.draw()

    def icon(self,name):
        if name in self.icons:return self.icons[name]
        result=None
        # Prototype names are labels, never arbitrary paths from telemetry.
        if name and all(c.isalnum() or c in '-_' for c in name):
            for package in ('base','space-age','quality','elevated-rails'):
                path=self.icon_root/package/'graphics/icons'/(name+'.png')
                if path.is_file():
                    try:
                        source=tk.PhotoImage(file=str(path))
                        # Factorio PNGs include horizontal mipmaps; crop the first square.
                        edge=min(source.width(),source.height())
                        square=tk.PhotoImage(width=edge,height=edge)
                        square.tk.call(str(square),'copy',str(source),'-from',0,0,edge,edge)
                        result=square.subsample(max(1,math.ceil(edge/32)))
                    except tk.TclError:pass
                    break
        self.icons[name]=result
        return result

    def inventory(self):
        self.items.delete('all');self.slot_hits=[]
        if not self.last['inventory_available']:
            self.inventory_status.set('Main inventory unavailable');return
        actual='slots' in self.last
        slots=self.last.get('slots',[dict(i,slot=n+1) for n,i in enumerate(self.last['inventory'])])
        capacity=min(self.last.get('capacity',len(slots)),200)
        partial=self.last.get('slots_truncated',False) or self.last['truncated']
        self.inventory_status.set(f'Player main inventory · {capacity} slots'+(' · partial' if partial else '')+('' if actual else ' · aggregate fallback'))
        lookup={v['slot']:v for v in slots};size=40;columns=10
        for i in range(capacity):
            x=(i%columns)*size+4;y=(i//columns)*size+4
            self.items.create_rectangle(x,y,x+36,y+36,fill='#3e4338',outline='#171b14',width=2)
            self.items.create_line(x+2,y+2,x+34,y+2,fill='#252b20',width=2)
            self.items.create_line(x+2,y+2,x+2,y+34,fill='#252b20',width=2)
            self.items.create_line(x+2,y+35,x+35,y+35,fill='#5d6553')
            self.items.create_line(x+35,y+2,x+35,y+35,fill='#5d6553')
            v=lookup.get(i+1)
            if v:
                image=self.icon(v['name'])
                if image:self.items.create_image(x+18,y+17,image=image)
                else:self.items.create_text(x+18,y+15,text='\n'.join(v['name'].split('-')[:2]),fill='#e0dfd3',font=('Segoe UI',7),width=34)
                self.items.create_text(x+34,y+35,anchor='se',text=str(v['count']),fill='white',font=('Segoe UI',9,'bold'))
                q=v['quality'];color=QUALITY_COLORS.get(q,'#dfd6aa')
                if q!='normal':
                    self.items.create_rectangle(x+2,y+2,x+11,y+11,fill=color,outline='')
                    self.items.create_text(x+7,y+7,text=q[0].upper(),fill='#111',font=('Segoe UI',6,'bold'))
                hint=f"Slot {i+1}: {v['name']} × {v['count']} · {q}"
            else:hint=f'Slot {i+1}: empty'
            self.slot_hits.append((x,y,hint))
        self.items.configure(scrollregion=(0,0,columns*size+8,math.ceil(capacity/columns)*size+8))

    def hover(self,e):
        y=self.items.canvasy(e.y)
        for x0,y0,hint in self.slot_hits:
            if x0<=e.x<x0+36 and y0<=y<y0+36:self.item_hint.set(hint);return

    def update_frame(self,data):
        if data['status']!='ok':self.available=False;return
        if self.last is not None and self.last['surface']!=data['surface']:
            for key in ('visited','failed','resources'):data[key]=[]
            data['objective']=data['proposal']=None
            self.offset={'x':0,'y':0}
        overlays=data.get('terrain',{}).get('overlays',{})
        for key,(index,label) in self.overlay_entries.items():
            available=overlays.get('available',{}).get(key,False)
            partial=overlays.get('partial',{}).get(key,False)
            self.overlay_menu.entryconfigure(index,state='normal' if available else 'disabled',label=label+(' · partial' if partial else '')+('' if available else ' — unavailable'))
        self.last=data;self.received=time.monotonic();self.available=True
        self.inventory();self.draw()

    def freshness(self,running):
        if self.last is None:return
        age=time.monotonic()-self.received
        state='Live' if running and self.available and age<=3 else 'Stale' if running else 'Session ended; last snapshot'
        partial=' · partial entities' if self.last.get('terrain',{}).get('partial') else ''
        self.status.set(f"{state} | {self.last['surface']} | tick {self.last['tick']} | {age:.1f}s old | charted terrain, live visible entities{partial}")

    def draw_raster(self,terrain,center,width,height,radius):
        key=(tuple(terrain['rows']),tuple(terrain['palette']),tuple(terrain['origin'].values()),
             center['x'],center['y'],width,height,radius)
        if getattr(self,'raster_key',None)!=key:
            pixels=raster_pixels(terrain,center,width,height,radius)
            self.map_image=tk.PhotoImage(data=f'P6 {width} {height} 255\n'.encode()+pixels,format='PPM')
            self.raster_key=key
        self.canvas.create_image(0,0,anchor='nw',image=self.map_image)

    def draw(self):
        self.canvas.delete('all')
        if self.last is None:
            self.canvas.create_text(15,15,anchor='nw',fill='white',text='Waiting for observed map data');return
        width,height=self.canvas.winfo_width(),self.canvas.winfo_height()
        player=self.last['position'];center={k:player[k]+self.offset[k] for k in ('x','y')};radius=float(self.zoom.get())
        def loc(p):return project(p,center,width,height,radius)
        scale=min(width,height)/(2*radius)
        terrain=self.last.get('terrain',{})
        if 'rows' in terrain:
            self.draw_raster(terrain,center,width,height,radius)
        for t in terrain.get('tiles',[]):
            x,y=loc(t)
            color=t.get('color',terrain_color(t['name']))
            if t.get('visible') is False:
                color='#'+''.join(f'{int(color[i:i+2],16)*2//3:02x}' for i in (1,3,5))
            step=terrain.get('step',2)
            self.canvas.create_rectangle(x,y,x+step*scale+1,y+step*scale+1,fill=color,outline='')
        overlays=terrain.get('overlays',{})
        self.canvas.create_rectangle(0,0,width,height,outline='',tags='overlay-boundary')
        for key in self.overlay_entries:
            if not self.layers[key].get() or not overlays.get('available',{}).get(key):continue
            for e in overlays[key]:
                x,y=loc(e)
                if key=='pollution':
                    if e['value']<=0:continue
                    red=min(220,80+int(25*math.log1p(e['value'])))
                    self.canvas.create_rectangle(x,y,x+e['width']*scale,y+e['height']*scale,fill=f'#{red:02x}3020',outline='',stipple='gray50')
                elif key=='electric':
                    r=e['radius']*scale
                    self.canvas.create_rectangle(x-r,y-r,x+r,y+r,outline='#78b8ed',stipple='gray25',fill='#447799')
                    for q in e['connections']:
                        tx,ty=loc(q);self.canvas.create_line(x,y,tx,ty,fill='#e0ca5b')
                elif key=='logistics':
                    for field,color in [('construction','#68b568'),('logistic','#db9b42')]:
                        r=e[field]*scale
                        self.canvas.create_rectangle(x-r,y-r,x+r,y+r,outline=color,dash=() if e['active'] else (3,3))
                elif key=='turrets':
                    r=e['radius']*scale
                    self.canvas.create_oval(x-r,y-r,x+r,y+r,outline='#df6672',dash=(3,3))
                else:
                    text=e['text'] or e.get('icon') or '(unnamed)'
                    self.canvas.create_rectangle(x-3,y-3,x+3,y+3,fill='#e8b45b',outline='#1a1b17')
                    self.canvas.create_text(x+7,y,anchor='w',text=text,fill='#f4e4b0',font=('Segoe UI',9,'bold'))
        for e in terrain.get('entities',[]):
            if not self.layers[e['kind']].get():continue
            x,y=loc(e)
            if not 0<=x<=width or not 0<=y<=height:continue
            kind=e['kind'];size=max(.65,scale*.5) if kind=='resource' else max(1,scale*.7)
            color=RESOURCE_COLORS.get(e['name'],'#be92b9') if kind=='resource' else {'enemy':'#ed4e42','building':'#67acc2','nature':'#34462a'}[kind]
            if kind=='resource':
                self.canvas.create_rectangle(x-size,y-size,x+size,y+size,fill=color,outline='')
            else:self.canvas.create_rectangle(x-size,y-size,x+size,y+size,fill=color,outline='')
        if self.layers['grid'].get():
            for axis in ('x','y'):
                extent=(width if axis=='x' else height)/(2*scale)
                start=math.floor((center[axis]-extent)/32)*32
                end=math.ceil((center[axis]+extent)/32)*32
                for value in range(start,end+1,32):
                    p=dict(center);p[axis]=value;x,y=loc(p)
                    self.canvas.create_line(x,0,x,height,fill='#706f54',dash=(2,4)) if axis=='x' else self.canvas.create_line(0,y,width,y,fill='#706f54',dash=(2,4))
        for key,color in [('visited','#a9aaa0'),('failed','#ff6861')]:
            if not self.layers['history'].get():continue
            for p in self.last[key]:
                x,y=loc(p);self.canvas.create_oval(x-2,y-2,x+2,y+2,outline=color)
        px,py=loc(player)
        for key,color in [('objective','#ffda65'),('proposal','#ff9c5c')]:
            p=self.last[key]
            if p and self.layers['goals'].get():
                x,y=loc(p);self.canvas.create_line(px,py,x,y,fill=color,dash=(4,4));self.canvas.create_rectangle(x-5,y-5,x+5,y+5,outline=color,width=2)
        self.canvas.create_polygon(px,py-8,px+6,py+6,px-6,py+6,fill='#5ed7f5',outline='#101d20')
        if self.layers['player_name'].get():self.canvas.create_text(px+10,py-10,anchor='w',text=overlays.get('player_name','Player'),fill='#5ed7f5')
        self.canvas.create_text(8,height-8,anchor='sw',fill='white',text=f"Player {player['x']:.2f}, {player['y']:.2f} | N up | Black: unobserved | Read-only")
        if not terrain:self.canvas.create_text(8,8,anchor='nw',fill='#ffda65',text='Terrain unavailable: rebuild display backend')

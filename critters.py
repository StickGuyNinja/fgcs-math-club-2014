import argparse
from random import *
import math
from geo2d.geometry import *
import itertools
from tkinter import *
import time
from intervalset import AngularIntervalSet
import sys,traceback

def random_color():
    return "#%02x%02x%02x" % (randrange(0,255),randrange(0,255),randrange(0,255))

def as_color(r,g,b):
    return "#%02x%02x%02x" % (255*r,255*g,255*b)

def gray(x):
    return as_color(x,x,x)

def Heading(dir,rho=None):
    return Vector(rho or 1.0,dir,coordinates="polar")

class DisplayObject:
    def __init__(self,world,loc):
        self.world = world
        self.location = loc
    def on_tick(self):
        pass
    def draw(self, canvas,s):
        pass
    def displacement_to(self,other):
        loc = other.location if hasattr(other, "location") else other
        return self.world.wrap(Vector(self.location,loc))

class Sound(DisplayObject):
    def __init__(self,world,loc,volume,text):
        DisplayObject.__init__(self,world,loc)
        self.volume = volume
        self.text   = text
        self.tk_id  = None
        self.age    = 1
        self.faded  = False
    def on_tick(self):
        self.age += 1
    def stipple(self):
        r = 100-(self.age*100)/self.volume
        if   r < 12: return 'gray12'
        elif r < 25: return 'gray25'
        elif r < 50: return 'gray50'
        elif r < 75: return 'gray75'
        else:        return 'gray75' #None
    def draw(self, canvas, s):
        if self.tk_id:
            canvas.delete(self.tk_id)
            self.tk_id = None    
        if self.age < self.volume:
            loc  = self.location
            self.tk_id = canvas.create_text(
                s*loc.x, s*loc.y-20,
                text=self.text,
                font=('Helvetica',int(s*((self.volume+self.age)/10)**2)),
                fill=gray(max(self.age/self.volume-0.2,0)),
                stipple=self.stipple()
                )
        else:
            self.faded = True

class PhysicalObject(DisplayObject):
    def __init__(self,world,loc):
        DisplayObject.__init__(self,world,loc)
        self.tk_id = None
        self.color = {"fill": "black"}
    def dump_status(self):
        print(self.location)
    def on_collision(self,dir,other):
        pass
    def radius(self):
        return 1
    def draw(self, canvas,s):
        r = self.radius()
        if r > 0:
            if self.tk_id is None:
                self.tk_id = canvas.create_oval(50, 50, s*2*r, s*2*r, **self.color)
            canvas.tag_lower(self.tk_id)
            loc = self.location
            canvas.coords(self.tk_id,      s*loc.x-s*r, s*loc.y-s*r,s*loc.x+s*r, s*loc.y+s*r)
        else:
            if self.tk_id:
                canvas.delete(self.tk_id)
                self.tk_id = None

class Critter(PhysicalObject):
    def __init__(self,world,brain_class,name):
        PhysicalObject.__init__(self,world,None)
        if isinstance(name,int):
            name = brain_class.owner + brain_class.code + str(name)
        self.name  = name
        self.heading = Heading(uniform(0.0,2*math.pi))
        profile = [uniform(0.5,0.8) for i in range(0,10)]
        self.shape   = [1.0,1.0,1.0]+profile+list(reversed(profile))
        self.size = 25
        self.color = {"fill":random_color(), "smooth":1, "stipple":'gray50'}
        self.tk_id = None
        self.brain = brain_class()
        self.dead = False
        self.last_spoke = -10
        self.sense_data = None
        self.whats_under = set()
        self.age = 0
        world.spawn(self)
    def dump_status(self):
        print(self.name)
        self.brain.dump_status()
        print(self.location)
    def on_tick(self):
        if not self.dead:
            self.age += 1
            for x in list(self.whats_under):
                if x.radius() <= 0 or self.distance_to(x) > self.radius() + x.radius():
                    self.whats_under.remove(x)
            self.sense_data = self.senses()
            self.size -= 0.01 + 0.1*self.heading.rho
            if self.size <= 0:
                self.die(sound="..nnn...nnn..nnn...",volume=6)
            else:
                self.act(self.brain_on_tick() or "Pass")
                self.location.translate(self.heading.x,self.heading.y)
                self.location = self.world.wrap(self.location)
    def on_collision(self,dir,other):
        self.whats_under.add(other)
        if isinstance(other,Food):
            self.act(self.brain_on_collision(dir,other) or "Eat")
        else:
            self.say("Ooof!")
            self.size  -= 0.1*self.size/(self.size+other.size) # Not quite right, 'cause one goes first
            if self.size <= 0:
                self.die(volume=0)
            else:
                self.location = self.world.wrap(Point(Vector(self.location)-dir*(other.size/self.size)))
                self.act(self.brain_on_collision(dir,other) or "Pass")
    def teleport_to(self,world,loc):
        self.world    = world
        self.location = loc
    def die(self,sound="Aaaaaaaaa...!",volume=20):
        self.size = 0
        if not self.dead:
            self.say(sound,volume=volume)
            self.dead = True
    def say(self,msg,volume=10):
        if not self.dead:
            if self.world.clock - self.last_spoke > 10:
                self.world.sound(self.location,volume,msg)
                self.last_spoke = self.world.clock
    def act(self,cmd):
        max_speed = 1.5
        sharpest_turn = 0.2
        if not cmd is None:
            word = cmd.split()
            if word[0] == "Stop":
                self.heading = self.heading.normalized*(1/10000)
            elif word[0] == "Go":
                self.heading = self.heading.normalized
            elif word[0] == "Turn":
                self.heading = Heading(self.heading.phi+sorted([-sharpest_turn,float(word[1]),sharpest_turn])[1],rho=self.heading.rho)
            elif word[0] == "Accelerate":
                self.heading *= float(word[1])
                if self.heading.rho > max_speed:
                    self.heading *= max_speed/self.heading.rho
            elif word[0] == "Attack":
                pass
            elif word[0] == "Eat":
                for f in self.whats_under:
                    if isinstance(f,Food) and f.value > 0:
                        self.say("Yum")
                        f.value -= 0.1
                        self.size += 0.1
                        break
            elif word[0] == "Pass":
                pass
            else:
                print("Unknown command: {}".format(cmd))
    def radius(self):
        return math.sqrt(self.size) if self.size > 0 else 0
    def relative_heading(self,x):
        return (x-self.heading.phi+math.pi) % 2*math.pi + math.pi
    def relative_heading_to(self,x):
        return self.relative_heading(self.displacement_to(x).phi)
    def distance_to(self,other):
        return self.displacement_to(other).rho
    def senses(self):
        return {
            'sight':   self.sight(), # set of tuples: (color,distance,direction,width,change)
            'smell':   set(), # set of tuples: (strength,smell,change)
            'hearing': set([(s.text,self.relative_heading_to(s),s.age) for s in self.world.sounds]),
            'taste':   set([type(x) for x in self.whats_under]),
            'gps':     self.location,
            'compass': self.heading.phi,
          }
    def sight(self):
        objects = []
        forward = self.heading.phi
        for o in self.world.neighbors[self]:
            if o != self:
               d = self.displacement_to(o)
               # We can only see things above our horizon, which we aproximate be saying they have
               #     to be within a quarter of the way around in either direction.
               if (d.x/self.world.width)**2 + (d.y/self.world.height)**2 < (1/4)**2:
                   # We can only see things in front of us
                   a = (d.phi-forward+math.pi) % (2*math.pi) - math.pi
                   delta_a = math.atan2(o.radius(),d.rho)
                   if abs(a)-abs(delta_a) < 1:
                       objects.append((d.rho,uniform(0.0,1.0),AngularIntervalSet(a-delta_a,a+delta_a),o))
        # We can only see things within a two radian field of view
        view_mask = AngularIntervalSet(-1,+1)
        sights = set()
        for dist,rand,image,obj in sorted(objects):
             # we see all of the object not blocked by something closer
             visable_part = view_mask.intersection(image)
             # the object blocks things that are further
             view_mask    = view_mask.intersection(image.inverse())
             for segment in visable_part.ranges():
                 sights.add((obj.color['fill'],dist,(segment[0]+segment[1])/2,segment[1]-segment[0],0))
             # stop when our field of view is full
             if view_mask.trivial(): break
        # TODO: figure out how to calculate change
        return sights
    def draw(self, canvas,s):
        if not self.dead:
            r    = self.radius()
            loc  = self.location
            phi  = self.heading.phi
            q    = 2*math.pi/len(self.shape)
            outline = [coord for a, d in enumerate(self.shape) for coord in (s*loc.x+s*r*d*math.cos(a*q+phi),s*loc.y+s*r*d*math.sin(a*q+phi))]
            if self.tk_id is None:
                self.tk_id = canvas.create_polygon(*outline, **self.color)
                self.tk_text_id = canvas.create_text(50,50, text=self.name)
                self.tk_eye_id   = canvas.create_oval(50, 50, s, s, fill = "white")
                self.tk_pupil_id = canvas.create_oval(50, 50, s, s, fill = "black", outline="blue")
            canvas.coords(self.tk_text_id, s*loc.x, s*loc.y)
            canvas.coords(self.tk_id,      *outline)
            x,y = outline[2],outline[3]
            pp = self.displacement_to(self.world.pits[0] if self.world.pits else self.world.random_location()).normalized
            canvas.coords(self.tk_eye_id,   x         -s, y         -s, x         +s, y          +s)
            canvas.coords(self.tk_pupil_id, x+s*pp.x/2-1, y+s*pp.y/2-1, x+s*pp.x/2+1, y+s*pp.y/2+1)
        elif self.tk_id:
            canvas.delete(self.tk_id)
            self.tk_id = None
            canvas.delete(self.tk_text_id)
            self.tk_text_id = None
            canvas.delete(self.tk_eye_id)
            self.tk_eye_id = None
            canvas.delete(self.tk_pupil_id)
            self.tk_pupil_id = None
    def brain_on_tick(self):
        try:
            return self.brain.on_tick(self.sense_data)
        except Exception as e:
            traceback.print_tb(sys.exc_info()[-1], limit=3)
            self.die()
    def brain_on_collision(self,dir,other):
        try:
            return self.brain.on_collision(dir,other,self.sense_data)
        except Exception as e:
            traceback.print_tb(sys.exc_info()[-1], limit=3)
            self.die()

class CritterBrain:
    code  = ''
    owner = None
    def dump_status(self):
        pass
    def on_collision(self,dir,other,senses):
        pass
    def on_attack(self,dir,attacker,senses):
        pass
    def on_tick(self,senses):
        pass

class Food(PhysicalObject):
    def __init__(self,world,loc,value):
        PhysicalObject.__init__(self,world,loc)
        self.value = value
        self.color = {"fill": "dark green", "outline": "green", "width":3}
    def on_tick(self):
        # Could spoil, spread, or...?
        pass
    def on_collision(self,dir,other):
        pass
    def radius(self):
        if self.value < 0: self.value = 0
        return math.sqrt(self.value)

class Pit(PhysicalObject):
    def __init__(self,world,loc):
        PhysicalObject.__init__(self,world,loc)
        print("Pit at ",self.location)
        #world.sound(self.location,5,"Aaha!")
        self.r = 10
        self.color = {"fill": "black", "outline": "dark red"}
    def on_tick(self):
        pass
    def on_collision(self,dir,other):
        other.location = self.location
        other.die()
    def radius(self):
        return self.r

class World:
    height = 100
    width  = 200
    def __init__(self,tick_time=0.1,tick_limit=-1,food=50,pits=0,warn=False):
        self.critters = []
        self.starting_critters = []
        self.world_view = WorldView(self,5)
        self.food = [Food(self,self.random_location(),randrange(2,16)) for i in range(0,food)]
        self.pits = [Pit(self,self.random_location()) for i in range(0,pits)]
        self.sounds = []
        self.clock = 0
        self.neighbors = None
        self.tick_time = tick_time
        self.tick_limit = tick_limit
        self.warn = warn
    def random_location(self):
        return Point(randrange(0,self.width),randrange(0,self.height))
    def spawn(self,critter):
        self.critters.append(critter)
        self.starting_critters.append(critter)
        critter.teleport_to(self,self.random_location())
    def dump_status(self):
        for c in self.critters:
             c.dump_status()
    def physical_objects(self):
        return self.critters + self.food + self.pits
    def display_objects(self):
        return self.physical_objects() + self.sounds
    def sound(self,loc,volume,text):
        self.sounds.append(Sound(self,loc,volume,text))
    def run(self):
        neighborhood_radius = min(self.height,self.width)/2
        stop_count = math.log(math.e*len(self.starting_critters))
        while self.world_view.window_open and self.clock != self.tick_limit and len(self.critters) > stop_count:
            loop_start = time.time()
            self.clock += 1
            self.sounds   = [s for s in self.sounds if not s.faded]
            self.food     = [f for f in self.food if f.value > 0]
            self.critters = [c for c in self.critters if not c.dead] 
            shuffle(self.critters)
            if self.clock % 10 == 0 or not self.neighbors:
                self.neighbors = {}
                for c in self.critters:
                    self.neighbors[c] = set()
                    others = set(self.physical_objects())
                    others.remove(c)
                    for o in others:
                        if c.distance_to(o) < neighborhood_radius:
                            self.neighbors[c].add(o)
            for c in self.display_objects():
                c.on_tick()
            for c in self.critters:
                for o in self.neighbors[c]:
                    if c.distance_to(o) < c.radius() + o.radius():
                        v = o.displacement_to(c).normalized
                        c.on_collision(-v,o)
                        o.on_collision( v,c)
            self.world_view.on_tick()
            excess_time = self.tick_time-(time.time()-loop_start)
            if excess_time > 0:
                time.sleep(excess_time)
            elif self.warn:
                print("Tick over time by ",-excess_time," seconds!")
    def wrap(self,p):
        h = self.height
        w = self.width
        if isinstance(p,Point):  return Point(p.x % w,p.y % h)
        if isinstance(p,Vector): return Vector((p.x+w/2) % w - w/2,(p.y+h/2) % h - h/2)
        return p
    def print_stats(self):
        print("Food remaining: ",sum(f.value for f in self.food))
        print("Brains available:   ",len(Brains.available))
        print("Critters at start:  ",len(self.starting_critters))
        print("Critters remaining: ",len(self.critters))
        for c in sorted(self.starting_critters,key=lambda c: (c.age,c.size),reverse=True):
            print("    %5s %6s  %5.1f" % (c.name,["alive","%5.2f" % (c.age*self.tick_time)][c.dead],c.size))

class WorldView:
    def __init__(self,world,scale):
        self.world = world
        self.scale = scale
        self.tk = Tk()
        self.tk.title("Critters")
        self.tk.resizable(0, 0)
        self.tk.wm_attributes("-topmost", 1)
        self.canvas_height = scale*world.height
        self.canvas_width  = scale*world.width
        self.canvas = Canvas(self.tk, width=self.canvas_width, height=self.canvas_height, highlightthickness=0)
        self.canvas.pack()
        self.tk.update()
        self.window_open = True
        def they_hit_close():
            self.window_open = False
        self.tk.protocol("WM_DELETE_WINDOW",they_hit_close)
        def menu(evt):
            tk = Tk()
            btnq = Button(tk, text="Quit", command=tk.destroy)
            btnq.pack({"side": "bottom"})
            tk.title('Menu')
            tk.resizable(0, 0)
            tk.wm_attributes("-topmost", 1)
            tk.update()
        self.canvas.bind_all('<KeyPress-m>', menu)
    def on_tick(self):
        if self.window_open:
            for sprite in self.world.display_objects():
                sprite.draw(self.canvas,self.scale)
            self.tk.update_idletasks()
            self.tk.update()

class Users:
    registered = []
    current = None
    initial = None
    def register(name):
        Users.registered.append(name)
        Users.current = name
        Users.initial = name[0:1]
    def initial(ch):
        Users.initial = ch

class Brains:
    registered = {}
    available = []
    def register(brain_class):
        u = Users.current
        if not u in Brains.registered.keys():
            Brains.registered[u] = []
        Brains.registered[u].append(brain_class)
        Brains.available.append(brain_class)
        brain_class.owner = Users.initial

parser = argparse.ArgumentParser()
parser.add_argument('-t', default=0.1, type=float)
parser.add_argument('-n', default= -1, type=int)
parser.add_argument('-c', default= 10, type=int)
parser.add_argument('-f', default=100, type=int)
parser.add_argument('-p', default=  0, type=int)
parser.add_argument('-w', default=False, action='store_true')

cmd = parser.parse_args()

import atexit
import glob,re

@atexit.register
def show_stats():
    global w
    w.print_stats()


for file in glob.glob("*_brains.py"):
    match = re.search('^(.+)_brains.py$', file)
    if match:
        Users.register(match.group(1))
        try:
            exec(compile(open(file, "r").read(), file, 'exec'))
        except Exception as e:
            traceback.print_exception(*sys.exc_info(),limit=1)

w = World(tick_time=cmd.t,tick_limit=cmd.n,food=cmd.f,pits=cmd.p,warn=cmd.w)
if True:
    [Critter(w,Brains.available[i % len(Brains.available)],i) for i in range(1,cmd.c+1)]
else:
    [Critter(w,choice(Brains.available),i) for i in range(1,cmd.c+1)]
w.run()

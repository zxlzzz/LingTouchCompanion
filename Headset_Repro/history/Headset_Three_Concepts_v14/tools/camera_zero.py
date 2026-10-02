from pathlib import Path
exec(Path(__file__).with_name('routes.py').read_text(encoding='utf-8').split('names=sys.argv[2:]')[0])
cx,cy,cz=design['camera_center'];cc=np.array([cx,cy,cz]);s,da=endpoint('LEAD__CS30_USB');e,db=endpoint('LEAD__Splitter_OUT');ang=math.radians(20);R=np.array([[1,0,0],[0,math.cos(ang),-math.sin(ang)],[0,math.sin(ang),math.cos(ang)]])
s=(s-cc)@R.T+cc;da=da@R.T
for i,o in enumerate(ob):
 if meta[o['name']]['owner'] in ['MOVE__CS30','MOVE__ICM42688P_LogicalEdges']:
  centers[i]=(centers[i]-cc)@R.T+cc;rotations[i]=R@rotations[i]
h=[[s[0],cy-30,s[2]+5],[-28,cy-30,cz+10],[14,cy-29,cz+10],[e[0],e[1],e[2]+16]]
segs,m=solve('USB_Camera_pose0',s,e,da,db,1.5,12,h,margin=1.6)
(D/'camera_zero.json').write_text(json.dumps(dict(segments=segs.tolist(),metrics=m),indent=2))

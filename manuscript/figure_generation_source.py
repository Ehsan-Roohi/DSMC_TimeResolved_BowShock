from __future__ import annotations
from pathlib import Path
import re, io, os, shutil, math, json, zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.colors import TwoSlopeNorm

ROOT=Path('/mnt/data/JFM2_MANUSCRIPT_DRAFT_V1')
FIG=ROOT/'figures'
DATA=ROOT/'data'
for p in [ROOT,FIG,DATA]: p.mkdir(parents=True,exist_ok=True)

R=0.1524
xc=R; yc=0.0

plt.rcParams.update({
    'font.family':'serif',
    'font.serif':['STIX Two Text','STIXGeneral','DejaVu Serif'],
    'mathtext.fontset':'stix',
    'font.size':8.5,
    'axes.labelsize':8.5,
    'axes.titlesize':9.0,
    'xtick.labelsize':7.5,
    'ytick.labelsize':7.5,
    'legend.fontsize':7.0,
    'figure.dpi':160,
    'savefig.dpi':400,
    'axes.linewidth':0.7,
    'lines.linewidth':1.25,
    'pdf.fonttype':42,
    'ps.fonttype':42,
    'svg.fonttype':'none',
})

CASE_INFO={
 'Kn0p01': {'Kn':0.01,'label':r'$Kn_D=0.01$','cache':'/mnt/data/_paperwork/disp/Kn0p01\\attached_field_cache.npz'},
 'Kn0p025':{'Kn':0.025,'label':r'$Kn_D=0.025$','cache':'/mnt/data/_paperwork/disp/Kn0p025\\attached_field_cache.npz'},
 'Kn0p050':{'Kn':0.05,'label':r'$Kn_D=0.05$','cache':'/mnt/data/_paperwork/disp/Kn0p050\\attached_field_cache.npz'},
}

def savefig(fig,name):
    fig.savefig(FIG/(name+'.pdf'),bbox_inches='tight')
    fig.savefig(FIG/(name+'.png'),bbox_inches='tight',dpi=400)
    plt.close(fig)

def panel_label(ax,label):
    ax.text(0.015,0.985,label,transform=ax.transAxes,ha='left',va='top',
            fontsize=9,fontweight='bold',
            bbox=dict(facecolor='white',edgecolor='none',alpha=0.75,pad=1.5),zorder=50)

def draw_cylinder(ax,face='white'):
    ax.add_patch(Circle((xc/R,yc/R),1.0,facecolor=face,edgecolor='black',lw=0.9,zorder=20))

def load_cache(case):
    z=np.load(CASE_INFO[case]['cache'],allow_pickle=True)
    return {k:z[k] for k in z.files}

def rho_inf(cache):
    xi=cache['xi']; cube=cache['cube'][:,0]
    return float(np.nanmedian(cube[:,:,xi>3.5]))

def load_marker(case,full=False):
    if case=='Kn0p01':
        p='/mnt/data/_paperwork/common/temporal_common200\\Kn0p01\\marker_arrays_m1_ang1.npz'
    else:
        p=f'/mnt/data/_paperwork/transition/temporal_full\\{case}\\marker_arrays_m1_ang1.npz'
    z=np.load(p)
    return {k:z[k] for k in z.files}

def load_cov(case):
    if case=='Kn0p01':
        p='/mnt/data/_paperwork/common/correlated_common200\\Kn0p01\\ang1\\inferred_covariances.npz'
    else:
        p=f'/mnt/data/_paperwork/transition/correlated_full\\{case}\\ang1\\inferred_covariances.npz'
    z=np.load(p)
    return {k:z[k] for k in z.files}

def corrmat(C):
    d=np.sqrt(np.maximum(np.diag(C),0))
    return np.clip(C/np.maximum(d[:,None]*d[None,:],1e-300),-1,1)

def att(m,phi):
    m=int(m)
    return (m+2*sum((m-k)*phi**k for k in range(1,m)))/(m*m)

def read_dat(path):
    lines=Path(path).read_text(errors='ignore').splitlines()
    names=re.findall(r'"([^"]+)"',lines[1])
    I,J=map(int,re.search(r'I=(\d+),\s*J=(\d+)',lines[2]).groups())
    arr=np.loadtxt(io.StringIO('\n'.join(lines[3:]))).reshape(J,I,len(names))
    return {n:arr[:,:,i] for i,n in enumerate(names)}

# -------------------------------------------------------------------------
# Fig 1: geometry, profile, and marker space-time
# -------------------------------------------------------------------------
c=load_cache('Kn0p01'); mean=np.nanmean(c['cube'][:,0],axis=0); ri=rho_inf(c)
X=c['xwin']/R; Y=c['ywin']/R; xi=c['xi']; th=c['theta']
mark=load_marker('Kn0p01'); Z=mark['s50_over_R'][:200]
t=mark['group_time_center_star'][:200]
Zc=Z-np.nanmean(Z,axis=0,keepdims=True)
fig=plt.figure(figsize=(7.25,2.65),constrained_layout=True)
gs=fig.add_gridspec(1,3,width_ratios=[1.18,0.9,1.35])
ax=fig.add_subplot(gs[0,0])
cf=ax.contourf(X,Y,mean/ri,levels=np.linspace(1,5.8,45),cmap='turbo',extend='both')
for j in np.linspace(0,len(th)-1,7,dtype=int):
    ax.plot(X[j],Y[j],color='white',lw=.45,alpha=.72,zorder=8)
idx0=np.argmin(abs(xi))
ax.plot(X[:,idx0],Y[:,idx0],color='black',lw=1.2,zorder=15)
ax.plot(X[:,idx0],Y[:,idx0],color='white',lw=.55,zorder=16)
draw_cylinder(ax)
ax.set_aspect('equal',adjustable='box'); ax.set_xlim(-1.0,.52); ax.set_ylim(0,1.95)
ax.set_xlabel(r'$x/R$'); ax.set_ylabel(r'$y/R$')
panel_label(ax,'(a)')
cb=fig.colorbar(cf,ax=ax,pad=.01,shrink=.82); cb.set_label(r'$\bar\rho/\rho_\infty$')

ax=fig.add_subplot(gs[0,1])
j=-1; s=c['swin'][j]/R; prof=mean[j]
up=float(np.nanmedian(prof[xi>3.3])); down=float(np.nanmedian(prof[xi<-.75])); q=(prof-up)/(down-up)
ax.plot(s,q,color='black',lw=1.7)
levels=[.1,.5,.9]; symbols=['10%','50%','90%']
for lv,lab,col in zip(levels,symbols,['#3b4cc0','#111111','#b40426']):
    k=int(np.nanargmin(abs(q-lv)))
    ax.scatter(s[k],q[k],s=22,color=col,zorder=10)
    ax.axvline(s[k],color=col,lw=.75,ls='--',alpha=.8)
    ax.text(s[k],lv+.055,lab,color=col,ha='center',va='bottom',fontsize=7)
ax.set_xlim(max(0,s.min()),min(1.25,s.max())); ax.set_ylim(-.05,1.08)
ax.set_xlabel(r'$s/R$ at stagnation ray'); ax.set_ylabel(r'$\rho^*=(\rho-\rho_{up})/(\rho_{down}-\rho_{up})$')
ax.grid(alpha=.2); panel_label(ax,'(b)')

ax=fig.add_subplot(gs[0,2])
q99=np.nanpercentile(abs(Zc),99)
im=ax.imshow(Zc.T,origin='lower',aspect='auto',extent=[t[0],t[-1],mark['theta_deg'][0],mark['theta_deg'][-1]],
             cmap='RdBu_r',vmin=-q99,vmax=q99,interpolation='nearest')
ax.set_xlabel(r'$t^*=tU_\infty/D$'); ax.set_ylabel(r'$\theta$ (deg)')
panel_label(ax,'(c)')
cb=fig.colorbar(im,ax=ax,pad=.01,shrink=.82); cb.set_label(r'$s_{50}^\prime/R$')
fig.suptitle('Shock-attached geometry and time-resolved displacement marker',fontsize=10.5,y=1.02)
savefig(fig,'fig01_geometry_marker')

# -------------------------------------------------------------------------
# Fig 2: artifact audit in attached coordinates
# -------------------------------------------------------------------------
rows=[
 ('Kn0p25','D',r'$Kn_D=0.25$: density'),
 ('Kn0p50','TRT',r'$Kn_D=0.50$: $T_{rot}$'),
]
fig,axes=plt.subplots(2,3,figsize=(7.25,4.5),constrained_layout=True)
for i,(case,var,rtitle) in enumerate(rows):
    old=read_dat(f'/mnt/data/_paperwork/campaign/{case}\\common200_{var}\\POD_mode_001.dat')
    newd=read_dat(f'/mnt/data/_paperwork/wall/campaign\\{case}\\common200_{var}\\POD_mode_001.dat')
    f=f'{var}_pod_mode_001'
    Eold=float(pd.read_csv(f'/mnt/data/_paperwork/campaign/{case}\\common200_{var}\\pod_energy.csv').energy_fraction.iloc[0])
    Enew=float(pd.read_csv(f'/mnt/data/_paperwork/wall/campaign\\{case}\\common200_{var}\\pod_energy.csv').energy_fraction.iloc[0])
    zo=old[f]; so=old['s']/R; zn=newd[f]; sn=newd['s']/R
    oldscale=max(np.nanpercentile(abs(zo),99.8),1e-300)
    newmask=(sn>=.02)&~((newd['X']==0)&(newd['Y']==0))
    newscale=max(np.nanpercentile(abs(zn[newmask]),99.8),1e-300)
    panels=[
      (old,np.clip(zo/oldscale,-1,1),'Original registered mode',Eold),
      (old,np.where(so<.02,np.clip(zo/oldscale,-1,1),np.nan),'Mode restricted to solid-side support',None),
      (newd,np.where(newmask,np.clip(zn/newscale,-1,1),np.nan),'Physical-domain mode',Enew),
    ]
    for j,(d,z,title,E) in enumerate(panels):
        ax=axes[i,j]
        cf=ax.contourf(d['xi'],d['theta_deg'],z,levels=np.linspace(-1,1,51),cmap='RdBu_r',extend='both')
        if j<2:
            # trace the s/R=0.02 physical-support boundary in the old map
            try: ax.contour(d['xi'],d['theta_deg'],so,levels=[.02],colors='black',linewidths=.8)
            except Exception: pass
        ax.set_xlabel(r'$\xi$')
        if j==0: ax.set_ylabel(r'$\theta$ (deg)')
        else: ax.set_yticklabels([])
        if i==0: ax.set_title(title,fontsize=8.4)
        txt=rtitle
        if E is not None: txt+=f'\n$E_1={100*E:.1f}\\%$'
        ax.text(.03,.96,txt,transform=ax.transAxes,va='top',ha='left',fontsize=7.3,
                bbox=dict(facecolor='white',edgecolor='none',alpha=.82,pad=1.4))
        panel_label(ax,f'({chr(97+i*3+j)})')
fig.colorbar(cf,ax=axes.ravel().tolist(),pad=.012,shrink=.80,label='normalized POD-mode amplitude')
fig.suptitle('Physical-support audit of the apparent low-rank structures',fontsize=10.5)
savefig(fig,'fig02_physical_support_audit')

# -------------------------------------------------------------------------
# Fig 3: mean and RMS density contours at low Kn
# -------------------------------------------------------------------------
fig,axes=plt.subplots(2,3,figsize=(7.25,4.55),constrained_layout=True)
for j,case in enumerate(['Kn0p01','Kn0p025','Kn0p050']):
    d=load_cache(case); cube=d['cube'][:,0]; ri=rho_inf(d); m=np.nanmean(cube,axis=0)/ri; rms=np.nanstd(cube,axis=0,ddof=1)/ri
    xx=d['xwin']/R; yy=d['ywin']/R
    cf=axes[0,j].contourf(xx,yy,m,levels=np.linspace(1,6.5,56),cmap='turbo',extend='both')
    idx=np.argmin(abs(d['xi']))
    axes[0,j].plot(xx[:,idx],yy[:,idx],color='white',lw=1.0)
    axes[0,j].plot(xx[:,idx],yy[:,idx],color='black',lw=.35)
    draw_cylinder(axes[0,j]); axes[0,j].set_aspect('equal',adjustable='box')
    axes[0,j].set_title(CASE_INFO[case]['label'])
    axes[0,j].set_xlabel(r'$x/R$')
    if j==0: axes[0,j].set_ylabel(r'$y/R$')
    else: axes[0,j].set_yticklabels([])
    rf=axes[1,j].contourf(xx,yy,rms,levels=np.linspace(0,.10,51),cmap='magma',extend='max')
    draw_cylinder(axes[1,j]); axes[1,j].set_aspect('equal',adjustable='box')
    axes[1,j].set_xlabel(r'$x/R$')
    if j==0: axes[1,j].set_ylabel(r'$y/R$')
    else: axes[1,j].set_yticklabels([])
    axes[0,j].set_xlim(np.nanmin(xx)-.05,.55); axes[1,j].set_xlim(np.nanmin(xx)-.05,.55)
    ymax=min(3.45,np.nanmax(yy)+.05); axes[0,j].set_ylim(0,ymax); axes[1,j].set_ylim(0,ymax)
    panel_label(axes[0,j],f'({chr(97+j)})')
    panel_label(axes[1,j],f'({chr(100+j)})')
fig.colorbar(cf,ax=axes[0,:].tolist(),shrink=.82,pad=.01,label=r'$\bar\rho/\rho_\infty$')
fig.colorbar(rf,ax=axes[1,:].tolist(),shrink=.82,pad=.01,label=r'$\rho_{rms}/\rho_\infty$')
fig.suptitle('Mean compression-layer geometry and raw DSMC fluctuation level',fontsize=10.5)
savefig(fig,'fig03_mean_rms_contours')

# -------------------------------------------------------------------------
# Fig 4: mean geometry and corrected modal dimensionality all Kn
# -------------------------------------------------------------------------
pod=pd.read_csv('/mnt/data/corrected_pod_summary.csv')
geom=pod.groupby('Kn')[['s_marker_over_R','delta_over_R']].first().reset_index()
labels={'common200_D':r'$\rho$','common200_MA':r'$M$','common200_TTR':r'$T_{tr}$',
        'common200_TRT':r'$T_{rot}$','common200_P':r'$p$','common200_multivariate':'combined'}
colors=plt.cm.viridis(np.linspace(.05,.95,len(labels)))
fig,axes=plt.subplots(1,3,figsize=(7.25,2.45),constrained_layout=True)
ax=axes[0]
ax.semilogx(geom.Kn,geom.s_marker_over_R,marker='o',label=r'$s_{50}/R$')
ax.semilogx(geom.Kn,geom.delta_over_R,marker='s',label=r'$\delta_{10-90}/R$')
ax.set_xlabel(r'$Kn_D$'); ax.set_ylabel('normalized length'); ax.grid(alpha=.25); ax.legend()
panel_label(ax,'(a)')
ax=axes[1]
for (run,lab),col in zip(labels.items(),colors):
    g=pod[pod.run==run].sort_values('Kn'); ax.semilogx(g.Kn,100*g.E1,marker='o',ms=3,label=lab,color=col)
ax.set_xlabel(r'$Kn_D$'); ax.set_ylabel(r'leading energy $E_1$ (\%)'); ax.grid(alpha=.25); panel_label(ax,'(b)')
ax=axes[2]
for (run,lab),col in zip(labels.items(),colors):
    g=pod[pod.run==run].sort_values('Kn'); ax.semilogx(g.Kn,g.N90,marker='o',ms=3,label=lab,color=col)
ax.set_xlabel(r'$Kn_D$'); ax.set_ylabel(r'modes for 90\% variance'); ax.grid(alpha=.25); panel_label(ax,'(c)')
handles,leg=axes[2].get_legend_handles_labels(); fig.legend(handles,leg,ncol=3,loc='upper center',bbox_to_anchor=(.68,1.09),frameon=False)
fig.suptitle('Continuous mean-layer broadening but high-rank corrected field fluctuations',fontsize=10.3,x=.48,y=1.12)
savefig(fig,'fig04_geometry_highrank')
pod.to_csv(DATA/'corrected_pod_summary.csv',index=False)

# -------------------------------------------------------------------------
# Fig 5: temporal coarse graining and covariance model
# -------------------------------------------------------------------------
summary_common=pd.read_csv('/mnt/data/_paperwork/common/correlated_common200\\correlated_noise_inference_summary.csv')
summary_full=pd.read_csv('/mnt/data/_paperwork/transition/correlated_full\\correlated_noise_inference_summary.csv')
case_sources={
 'Kn0p01':('/mnt/data/_paperwork/common/temporal_common200\\Kn0p01\\coarse_graining_summary.csv',summary_common),
 'Kn0p025':('/mnt/data/_paperwork/transition/temporal_full\\Kn0p025\\coarse_graining_summary.csv',summary_full),
 'Kn0p050':('/mnt/data/_paperwork/transition/temporal_full\\Kn0p050\\coarse_graining_summary.csv',summary_full),
}
fig,axes=plt.subplots(2,3,figsize=(7.25,4.45),constrained_layout=True)
for j,case in enumerate(case_sources):
    p,sm=case_sources[case]; d=pd.read_csv(p); d=d[(d.quantity=='center')&(d.angular_smoothing_rays==1)].sort_values('group_size')
    r=sm[(sm.case==case)&(sm.angular_smoothing_rays==1)].iloc[0]
    m=d.group_size.to_numpy(float); mf=np.geomspace(1,16,150)
    point=(np.array([att(x,r.phi_physical) for x in mf])*r.trace_physical + np.array([att(x,r.phi_noise) for x in mf])*r.trace_noise)/60
    pointp=np.array([att(x,r.phi_physical) for x in mf])*r.trace_physical/60
    pointn=np.array([att(x,r.phi_noise) for x in mf])*r.trace_noise/60
    glob=np.array([att(x,r.phi_physical) for x in mf])*r.global_physical + np.array([att(x,r.phi_noise) for x in mf])*r.global_noise
    globp=np.array([att(x,r.phi_physical) for x in mf])*r.global_physical
    globn=np.array([att(x,r.phi_noise) for x in mf])*r.global_noise
    ax=axes[0,j]
    ax.loglog(m,d.mean_point_variance,'o',color='black',label='measured')
    ax.loglog(mf,point,color='#1f77b4',label='two-component fit')
    ax.loglog(mf,pointp,ls='--',color='#d62728',label='physical part')
    ax.loglog(mf,pointn,ls=':',color='#2ca02c',label='sampling part')
    ax.set_title(CASE_INFO[case]['label']); ax.set_xlabel('averaging group $m$')
    if j==0: ax.set_ylabel(r'mean pointwise variance')
    ax.grid(alpha=.2,which='both'); panel_label(ax,f'({chr(97+j)})')
    ax=axes[1,j]
    ax.loglog(m,d.global_series_std.to_numpy()**2,'o',color='black')
    ax.loglog(mf,glob,color='#1f77b4')
    ax.loglog(mf,globp,ls='--',color='#d62728')
    ax.loglog(mf,np.maximum(globn,1e-14),ls=':',color='#2ca02c')
    ax.set_xlabel('averaging group $m$')
    if j==0: ax.set_ylabel(r'angular-mean variance')
    ax.grid(alpha=.2,which='both'); panel_label(ax,f'({chr(100+j)})')
handles,lg=axes[0,0].get_legend_handles_labels(); fig.legend(handles,lg,ncol=4,loc='upper center',bbox_to_anchor=(.5,1.04),frameon=False)
fig.suptitle('Temporal coarse graining separates persistent covariance from correlated sampling fluctuations',fontsize=10.3,y=1.08)
savefig(fig,'fig05_temporal_coarse_graining')

# -------------------------------------------------------------------------
# Fig 6: physical correlation matrices and mode mapped on front
# -------------------------------------------------------------------------
fig,axes=plt.subplots(2,3,figsize=(7.25,4.65),constrained_layout=True)
for j,case in enumerate(['Kn0p01','Kn0p025','Kn0p050']):
    cv=load_cov(case); theta=cv['theta_deg']; C=cv['C_physical']; Rho=corrmat(C)
    im=axes[0,j].imshow(Rho,origin='lower',extent=[theta[0],theta[-1],theta[0],theta[-1]],vmin=-1,vmax=1,cmap='RdBu_r',aspect='equal')
    axes[0,j].set_title(CASE_INFO[case]['label'] + ('' if case!='Kn0p050' else ' (diagnostic)'))
    axes[0,j].set_xlabel(r'$\theta\prime$ (deg)')
    if j==0: axes[0,j].set_ylabel(r'$\theta$ (deg)')
    else: axes[0,j].set_yticklabels([])
    panel_label(axes[0,j],f'({chr(97+j)})')
    d=load_cache(case); idx=np.argmin(abs(d['xi'])); x=d['xwin'][:,idx]/R; y=d['ywin'][:,idx]/R
    mode=cv['physical_mode1'].copy();
    if np.nanmean(mode)<0: mode=-mode
    ev=np.linalg.eigvalsh(C); amp=np.sqrt(max(ev[-1],0))*mode
    rr=np.sqrt((x-1)**2+y*y); ex=(x-1)/rr; ey=y/rr
    axes[1,j].plot(x,y,color='black',lw=1.1,label='mean front')
    axes[1,j].plot(x+amp*ex,y+amp*ey,color='#b40426',lw=1.1,label=r'$+1\sigma$ mode')
    axes[1,j].plot(x-amp*ex,y-amp*ey,color='#3b4cc0',lw=1.1,label=r'$-1\sigma$ mode')
    sc=axes[1,j].scatter(x,y,c=mode,cmap='RdBu_r',s=13,edgecolor='none',zorder=8)
    draw_cylinder(axes[1,j]); axes[1,j].set_aspect('equal',adjustable='box')
    axes[1,j].set_xlim(np.nanmin(x)-.15,.55); axes[1,j].set_ylim(0,np.nanmax(y)+.1)
    axes[1,j].set_xlabel(r'$x/R$')
    if j==0: axes[1,j].set_ylabel(r'$y/R$')
    else: axes[1,j].set_yticklabels([])
    panel_label(axes[1,j],f'({chr(100+j)})')
fig.colorbar(im,ax=axes[0,:].tolist(),pad=.012,shrink=.78,label='inferred physical correlation')
fig.colorbar(sc,ax=axes[1,:].tolist(),pad=.012,shrink=.78,label='normalized mode amplitude')
axes[1,0].legend(loc='lower left',fontsize=6.5)
fig.suptitle('Noise-separated angular covariance and the inferred collective displacement shape',fontsize=10.4)
savefig(fig,'fig06_covariance_collective_mode')

# -------------------------------------------------------------------------
# Fig 7: marker space-time and mode projection
# -------------------------------------------------------------------------
fig,axes=plt.subplots(2,3,figsize=(7.25,4.45),constrained_layout=True)
for j,case in enumerate(['Kn0p01','Kn0p025','Kn0p050']):
    mk=load_marker(case); n=200; theta=mk['theta_deg']; time=mk['group_time_center_star'][:n]; X0=mk['s50_over_R'][:n]
    Xc=X0-np.nanmean(X0,axis=0,keepdims=True)
    cv=load_cov(case); mode=cv['physical_mode1'].copy();
    if np.nanmean(mode)<0: mode=-mode
    mode=mode/np.linalg.norm(mode)
    a=np.nan_to_num(Xc)@mode; rec=np.outer(a,mode)
    q=np.nanpercentile(abs(Xc),99)
    im=axes[0,j].imshow(Xc.T,origin='lower',aspect='auto',extent=[time[0],time[-1],theta[0],theta[-1]],cmap='RdBu_r',vmin=-q,vmax=q)
    axes[0,j].set_title(CASE_INFO[case]['label']); axes[0,j].set_xlabel(r'$t^*$')
    if j==0: axes[0,j].set_ylabel(r'$\theta$ (deg)')
    else: axes[0,j].set_yticklabels([])
    panel_label(axes[0,j],f'({chr(97+j)})')
    qr=np.nanpercentile(abs(rec),99)
    ir=axes[1,j].imshow(rec.T,origin='lower',aspect='auto',extent=[time[0],time[-1],theta[0],theta[-1]],cmap='RdBu_r',vmin=-qr,vmax=qr)
    axes[1,j].set_xlabel(r'$t^*$')
    if j==0: axes[1,j].set_ylabel(r'$\theta$ (deg)')
    else: axes[1,j].set_yticklabels([])
    panel_label(axes[1,j],f'({chr(100+j)})')
fig.colorbar(im,ax=axes[0,:].tolist(),pad=.012,shrink=.78,label=r'raw $s_{50}^\prime/R$ (case-scaled)')
fig.colorbar(ir,ax=axes[1,:].tolist(),pad=.012,shrink=.78,label='projection on inferred mode (case-scaled)')
fig.suptitle('Angular-time displacement maps: raw marker field and collective-mode projection',fontsize=10.4)
savefig(fig,'fig07_marker_spacetime')

# -------------------------------------------------------------------------
# Fig 8: multimoment correlation matrices and time traces
# -------------------------------------------------------------------------
fig,axes=plt.subplots(2,3,figsize=(7.25,4.55),constrained_layout=True)
for j,case in enumerate(['Kn0p01','Kn0p025','Kn0p050']):
    cm=pd.read_csv(f'/mnt/data/_paperwork/disp/{case}\\amplitude_correlation_matrix.csv',index_col=0)
    im=axes[0,j].imshow(cm.to_numpy(),vmin=-1,vmax=1,cmap='RdBu_r')
    names=['marker',r'$\rho$',r'$M$',r'$T_{tr}$',r'$p$']
    axes[0,j].set_xticks(range(5),names,rotation=45,ha='right'); axes[0,j].set_yticks(range(5),names if j==0 else [])
    axes[0,j].set_title(CASE_INFO[case]['label']); panel_label(axes[0,j],f'({chr(97+j)})')
    ts=pd.read_csv(f'/mnt/data/_paperwork/disp/{case}\\displacement_amplitude_timeseries.csv')
    cols=['marker_over_R','D_reference_mode_amp_over_R','P_reference_mode_amp_over_R']
    labs=['marker',r'full-field $\rho$',r'full-field $p$']
    for col,lab in zip(cols,labs):
        x=ts[col].to_numpy(float); z=(x-np.nanmean(x))/np.nanstd(x)
        axes[1,j].plot(ts.time_star,z,label=lab,lw=.8)
    axes[1,j].set_xlabel(r'$t^*$');
    if j==0: axes[1,j].set_ylabel('standardized amplitude')
    axes[1,j].grid(alpha=.2); panel_label(axes[1,j],f'({chr(100+j)})')
fig.colorbar(im,ax=axes[0,:].tolist(),pad=.012,shrink=.78,label='correlation')
axes[1,0].legend(ncol=1,fontsize=6.5,loc='upper right')
fig.suptitle('Full-field multi-moment validation of the displacement coordinate',fontsize=10.4)
savefig(fig,'fig08_multimoment_validation')

# -------------------------------------------------------------------------
# Fig 9: conditional composite density reconstruction (Kn .01, .025)
# -------------------------------------------------------------------------
fig,axes=plt.subplots(2,3,figsize=(7.25,4.35),constrained_layout=True)
for i,case in enumerate(['Kn0p01','Kn0p025']):
    d=load_cache(case); cube=d['cube'][:,0].astype(float); mean=np.nanmean(cube,axis=0); qprime=cube-mean[None]
    ri=rho_inf(d)
    ts=pd.read_csv(f'/mnt/data/_paperwork/disp/{case}\\displacement_amplitude_timeseries.csv')
    marker=ts.marker_over_R.to_numpy(float)
    lo=np.nanquantile(marker,.15); hi=np.nanquantile(marker,.85)
    actual=.5*(np.nanmean(qprime[marker>=hi],axis=0)-np.nanmean(qprime[marker<=lo],axis=0))/ri
    fld=np.load(f'/mnt/data/_paperwork/disp/{case}\\displacement_template_fields.npz',allow_pickle=True)
    vars_=[str(x) for x in fld['variables']]; vi=vars_.index('D')
    tpl=fld['reference_envelope'][:,None]*(-fld['mean_gradients_per_m'][vi])/ri
    w=fld['density_weights']; good=np.isfinite(actual)&np.isfinite(tpl)&(w>0)
    amp=float(np.sum(w[good]*actual[good]*tpl[good])/np.sum(w[good]*tpl[good]**2))
    model=amp*tpl; resid=actual-model
    frac=float((np.sum(w[good]*actual[good]*tpl[good])**2)/(np.sum(w[good]*actual[good]**2)*np.sum(w[good]*tpl[good]**2)))
    q=np.nanpercentile(abs(actual[np.isfinite(actual)]),99)
    for j,(z,title) in enumerate([(actual,'conditional density fluctuation'),(model,'translation-template reconstruction'),(resid,'residual')]):
        ax=axes[i,j]; cf=ax.contourf(d['xi'],d['theta'],z,levels=np.linspace(-q,q,51),cmap='RdBu_r',extend='both')
        ax.set_xlabel(r'$\xi$');
        if j==0: ax.set_ylabel(r'$\theta$ (deg)')
        else: ax.set_yticklabels([])
        if i==0: ax.set_title(title,fontsize=8.3)
        panel_label(ax,f'({chr(97+i*3+j)})')
        if j==1: ax.text(.03,.06,f'weighted $R^2={frac:.3f}$',transform=ax.transAxes,fontsize=7,
                         bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=1.2))
    axes[i,0].text(.03,.92,CASE_INFO[case]['label'],transform=axes[i,0].transAxes,fontsize=8,
                   bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=1.2))
fig.colorbar(cf,ax=axes.ravel().tolist(),pad=.012,shrink=.78,label=r'$\rho^\prime/\rho_\infty$')
fig.suptitle('Conditional full-field reconstruction of the collective density displacement',fontsize=10.4)
savefig(fig,'fig09_density_template_reconstruction')

# -------------------------------------------------------------------------
# Fig 10: statistical identifiability and limits
# -------------------------------------------------------------------------
slide=pd.read_csv('/mnt/data/_paperwork/gate/tables/corrected_sliding_window_robustness.csv')
power=pd.read_csv('/mnt/data/_paperwork/gate/tables/corrected_power_curves.csv')
excl=pd.read_csv('/mnt/data/_paperwork/gate/tables/corrected_exclusion_limits.csv')
fig=plt.figure(figsize=(7.25,4.75),constrained_layout=True)
gs=fig.add_gridspec(2,2,height_ratios=[1.15,1])
ax=fig.add_subplot(gs[0,:])
case_order=['Kn0p025','Kn0p050','Kn0p075','Kn0p10','Kn0p15']; ypos={c:i for i,c in enumerate(case_order)}
for case in case_order:
    g=slide[slide.case==case].sort_values('time_start_star'); x=.5*(g.time_start_star+g.time_end_star)
    sc=ax.scatter(x,np.full(len(g),ypos[case]),c=g.delta_aicc,cmap='coolwarm',vmin=-20,vmax=60,s=85,marker='s')
    pp=g.strict_window_pass_corrected.astype(bool).to_numpy(); ax.scatter(x[pp],np.full(pp.sum(),ypos[case]),marker='*',s=55,color='black',zorder=10)
ax.set_yticks(range(len(case_order)),[CASE_INFO.get(c,{'label':c})['label'] for c in case_order])
ax.set_xlabel(r'window-centre time $t^*$'); ax.set_ylabel('case'); ax.grid(alpha=.15,axis='x'); panel_label(ax,'(a)')
cb=fig.colorbar(sc,ax=ax,pad=.01,shrink=.85); cb.set_label(r'$\Delta AIC_c$')
ax=fig.add_subplot(gs[1,0])
for case,g in power[power.criterion=='reference'].groupby('case'):
    ax.plot(g.amplitude_multiplier,g.power,marker='o',ms=3,label=CASE_INFO.get(case,{'label':case})['label'])
ax.axhline(.9,ls='--',color='black',lw=.8); ax.axvline(1,ls=':',color='black',lw=.8)
ax.set_xlabel(r'injected amplitude / $Kn_D=0.01$ amplitude'); ax.set_ylabel('detection power'); ax.set_ylim(-.03,1.03); ax.grid(alpha=.2); panel_label(ax,'(b)')
ax.legend(fontsize=5.8,ncol=2,loc='lower right')
ax=fig.add_subplot(gs[1,1])
g=excl[excl.criterion=='reference'].copy(); kmap={'Kn0p025':.025,'Kn0p050':.05,'Kn0p075':.075,'Kn0p10':.1,'Kn0p15':.15}; g['Kn']=g.case.map(kmap)
y=g.U90_over_reference.fillna(6.3).to_numpy(); ax.semilogx(g.Kn,y,marker='o')
for xx,yy,val in zip(g.Kn,y,g.U90_over_reference):
    if not np.isfinite(val): ax.annotate('>6',xy=(xx,yy),xytext=(0,4),textcoords='offset points',ha='center',fontsize=7)
ax.axhline(1,ls=':',color='black',lw=.8); ax.set_ylim(0,6.8); ax.set_xlabel(r'$Kn_D$'); ax.set_ylabel(r'$U_{90}/A_{ref}$'); ax.grid(alpha=.2); panel_label(ax,'(c)')
fig.suptitle('Persistence and detectability limits beyond the resolved near-continuum regime',fontsize=10.3)
savefig(fig,'fig10_identifiability_limits')
slide.to_csv(DATA/'corrected_sliding_window_robustness.csv',index=False)
power.to_csv(DATA/'corrected_power_curves.csv',index=False)
excl.to_csv(DATA/'corrected_exclusion_limits.csv',index=False)

# Copy key tables
shutil.copy('/mnt/data/_paperwork/disp/all_cases_displacement_template_metrics.csv',DATA/'displacement_template_metrics.csv')
shutil.copy('/mnt/data/_paperwork/disp/all_cases_multimoment_consensus.csv',DATA/'multimoment_consensus.csv')
shutil.copy('/mnt/data/_paperwork/common/correlated_common200\\correlated_noise_inference_summary.csv',DATA/'common200_correlated_noise_summary.csv')
shutil.copy('/mnt/data/_paperwork/transition/correlated_full\\correlated_noise_inference_summary.csv',DATA/'full_record_correlated_noise_summary.csv')
print('Generated figures in',FIG)

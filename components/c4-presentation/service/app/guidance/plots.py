"""Standard Matplotlib research plots from recorded synthetic evaluations only."""
import argparse
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot(directory):
    directory=Path(directory).resolve()
    root=Path(__file__).resolve().parents[3]
    if not directory.is_relative_to(root) or "pp1-learning" not in directory.parts:raise ValueError("C4 pp1-learning report required")
    report=json.loads((directory/'report.json').read_text(encoding='utf-8'))
    rows=report['aggregates'];final=max(r['episode'] for r in rows)
    def save(name,title,ylabel):
        plt.title('SYNTHETIC - '+title);plt.ylabel(ylabel);plt.grid(alpha=.2);plt.tight_layout()
        plt.savefig(directory/(name+'.svg'));plt.savefig(directory/(name+'.png'),dpi=150);plt.close()
    for metric,name,title in [('expected_reward','learning','held-out learning curve'),('regret','regret','expected reward gap to simulator oracle')]:
        plt.figure(figsize=(8,4.5))
        for variant in ('416','451','516','525'):
            v=[r for r in rows if r['variant']==variant];x=[r['episode'] for r in v]
            y=[r['metrics'][metric]['mean'] for r in v];e=[r['metrics'][metric]['ci95_half_width'] or 0 for r in v]
            plt.errorbar(x,y,yerr=e,marker='o',label=variant+' features',capsize=3)
        if metric=='expected_reward':
            first=next(r for r in rows if r['variant']=='525')
            for key,color,style in [('standard','black','--'),('minimal','saddlebrown',':'),('maximal','purple','--'),('random','gray','-.')]:plt.axhline(first['metrics'][key]['mean'],linestyle=style,color=color,alpha=.7,label=key)
        plt.xlabel('Training observations');plt.legend(fontsize=8,ncol=2);save(name,title,'Simulated expected reward' if metric=='expected_reward' else 'Simulated expected regret')
    v=next(r for r in rows if r['variant']=='525' and r['episode']==final)
    keys=['expected_reward','standard','minimal','maximal','random']
    plt.figure(figsize=(8,4.5));plt.bar(['LinTS 525',*keys[1:]],[v['metrics'][k]['mean'] for k in keys],yerr=[v['metrics'][k]['ci95_half_width'] or 0 for k in keys],capsize=4)
    save('baselines','final baseline comparison (95% t intervals across seeds)','Simulated expected reward')
    finals=[r for r in rows if r['episode']==final]
    plt.figure(figsize=(8,4.5));plt.bar([r['variant'] for r in finals],[r['metrics']['expected_reward']['mean'] for r in finals],yerr=[r['metrics']['expected_reward']['ci95_half_width'] or 0 for r in finals],capsize=4)
    plt.xlabel('Feature count');save('ablation','encoder ablation - identical schedules and held-out cases','Simulated expected reward')
    evaluations=[r for r in report['evaluations'] if r['variant']=='525']
    dimensions=next(iter(evaluations))['evaluation']['dimensions'];labels=[];series={}
    for episode in report['checkpoints']:
        selected=[r['evaluation']['dimensions'] for r in evaluations if r['episode']==episode]
        values=[]
        for d,states in dimensions.items():
            for s in states:
                if episode==report['checkpoints'][0]:labels.append(d+':'+s)
                values.append(float(np.mean([x[d][s]/report['evaluation_cases'] for x in selected])))
        series[episode]=values
    plt.figure(figsize=(11,5));x=np.arange(len(labels));width=.8/len(series)
    for i,(episode,values) in enumerate(series.items()):plt.bar(x+i*width,values,width,label='n='+str(episode))
    plt.xticks(x+.3,labels,rotation=45,ha='right',fontsize=8);plt.legend(fontsize=8);save('distribution','scaffold state selection across checkpoints','Fraction of held-out cases')
    plt.figure(figsize=(8,4));
    for variant in ('416','451','516','525'):
        v=[r for r in rows if r['variant']==variant];plt.plot([r['episode'] for r in v],[r['metrics']['violations']['mean'] for r in v],marker='o',label=variant)
    plt.ylim(-.01,.1);plt.xlabel('Training observations');plt.legend();save('constraints','feasibility/accessibility violations','Violation rate')
    table=''.join('<tr><td>'+r['variant']+'</td><td>'+str(r['episode'])+'</td><td>'+format(r['metrics']['expected_reward']['mean'],'.4f')+'</td><td>'+format(r['metrics']['regret']['mean'],'.4f')+'</td></tr>' for r in rows)
    images=''.join('<h2>'+name+'</h2><img style="max-width:100%" src="'+name+'.svg" alt="Synthetic '+name+' plot">' for name in ('learning','baselines','regret','distribution','ablation','constraints'))
    document='<html lang="en"><meta charset="utf-8"><title>C4 PP1 SYNTHETIC research</title><body style="font:16px sans-serif;max-width:1100px;margin:32px auto"><h1>SYNTHETIC PP1 learning report</h1><p>Author-defined hypotheses. External expert review pending. These are not citizen comprehension or accuracy results.</p><p>Seeds: '+html.escape(str(report['seeds']))+'</p><table border="1"><tr><th>Features</th><th>Observations</th><th>Expected reward</th><th>Regret</th></tr>'+table+'</table>'+images+'<h2>Limitations</h2><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in report['limitations'])+'</ul></body></html>'
    (directory/'report.html').write_text(document,encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);a=p.parse_args();plot(a.directory)

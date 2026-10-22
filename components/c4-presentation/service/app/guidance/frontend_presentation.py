"""Source-derived frontend organization. Browsing never proves task completion."""
from app.guidance.composition import compose


def eligible_ids(graph, choices, *, require_choice=False):
    ids={a.action_id for a in graph.actions}
    for branch in graph.branch_groups:
        selected=choices.get(branch.group_id)
        if branch.selection=="AND":continue
        if selected is None:
            if require_choice:
                ids-={a for o in branch.options for a in o.action_ids}
            continue
        ids-={a for o in branch.options if o.option_id not in selected for a in o.action_ids}
    return ids


def ordering(source, choices):
    graph=source.graph
    if graph.completeness.prerequisites!="complete":return {a.action_id:None for a in graph.actions}
    allowed=eligible_ids(graph,choices)
    predecessors={a:set() for a in allowed}
    for edge in graph.action_prerequisites:
        if edge.source_id in allowed and edge.target_id in allowed:predecessors[edge.target_id].add(edge.source_id)
    branches={b.group_id:b for b in graph.branch_groups}
    def leaves(expr):
        if expr.kind=="action":return {expr.ref}&allowed
        if expr.kind=="selected_option_of":
            return {a for o in branches[expr.ref].options for a in o.action_ids}&allowed
        return set().union(*(leaves(c) for c in expr.children))
    for join in source.relationships.joins if source.relationships else ():
        if join.target in predecessors:predecessors[join.target].update(leaves(join.requirement))
    layers={};pending=set(predecessors)
    while pending:
        ready={a for a in pending if predecessors[a]<=layers.keys()}
        if not ready:return {a.action_id:None for a in graph.actions}
        for aid in ready:layers[aid]=max((layers[p] for p in predecessors[aid]),default=0)+1
        pending-=ready
    return {a.action_id:layers.get(a.action_id) for a in graph.actions}


def navigation(source, document, state):
    graph=source.graph;choices=state['routes'];layers=ordering(source,choices)
    allowed=eligible_ids(graph,choices,require_choice=True)
    ordered=sorted((a for a in graph.actions if a.action_id in allowed),key=lambda a:(layers[a.action_id] or 0,a.action_id))
    entries=[]
    byid={a.action_id:a for a in graph.actions}
    for a in graph.actions:
        label=None;route_position=None
        if layers[a.action_id] is not None:
            if a.applicability.branch_group_id:
                peers=sorted((b for b in graph.actions if b.applicability.branch_group_id==a.applicability.branch_group_id and b.applicability.branch_option_id==a.applicability.branch_option_id),key=lambda b:(layers[b.action_id] or 0,b.action_id))
                local_layers=sorted({layers[b.action_id] for b in peers if layers[b.action_id] is not None})
                route_position=local_layers.index(layers[a.action_id])+1
                label='Within this route: '+str(route_position)
            else:label='Dependency layer '+str(layers[a.action_id])
        entries.append({'action_id':a.action_id,'layer':layers[a.action_id], 'label':label,
                        'branch_id':a.applicability.branch_group_id,'option_id':a.applicability.branch_option_id,
                        'route_layer':route_position,'available_for_navigation':a.action_id in allowed,
                        'orientation_only':True})
    ids=[a.action_id for a in ordered];active=state.get('active_action_id')
    if active not in ids:active=ids[0] if ids else None
    index=ids.index(active) if active else None
    return {'mode':document['configuration']['navigation'],'entries':entries,'active_action_id':active,
            'browsing_action_ids':ids,'previous_action_id':ids[index-1] if index is not None and index>0 else None,
            'next_action_id':ids[index+1] if index is not None and index+1<len(ids) else None,
            'browsing_position':index+1 if index is not None else None,'browsing_count':len(ids),
            'unresolved_route_ids':[b.group_id for b in graph.branch_groups if b.selection!='AND' and b.group_id not in choices],
            'numbering_enabled':all(v is not None for aid,v in layers.items() if aid in allowed),
            'order_semantics':'Browsing orientation only. Peer layers do not establish parallelism; raw joins preserve AND/OR/selected-route meaning. No completion is inferred.'}


def relationship_aid(source, document):
    labels=document['map_labels'];notes=[];inline={a['id']:[] for a in document['actions']}
    def add(target,kind,text,evidence,relation):
        cue={'kind':kind,'text':text,'evidence_ids':list(evidence),'relation_id':relation}
        notes.append(text)
        if target in inline:inline[target].append(cue)
    for e in source.graph.action_prerequisites:
        add(e.target_id,'before','Before this: '+labels[e.source_id],e.evidence_ids,e.edge_id)
    branches={b.group_id:b for b in source.graph.branch_groups}
    def expression(expr):
        if expr.kind=='action':return labels[expr.ref]
        if expr.kind=='selected_option_of':
            b=branches[expr.ref]
            options=[' / '.join(labels[a] for a in o.action_ids) for o in b.options]
            return 'The applicable route ('+' OR '.join(options)+')'
        word='All of: ' if expr.kind=='all_of' else 'At least one of: '
        return word+'; '.join(expression(c) for c in expr.children)
    for i,j in enumerate(source.relationships.joins if source.relationships else ()):
        add(j.target,'join','Before '+labels[j.target]+': '+expression(j.requirement),j.evidence_ids,'overlay-join:'+str(i))
    for group in source.graph.parallel_groups:
        text='Verified parallel work: '+'; '.join(labels[a] for a in group.action_ids)
        for aid in group.action_ids:add(aid,'parallel',text,group.evidence_ids,group.group_id)
    for i,group in enumerate(source.relationships.parallel_areas if source.relationships else ()):
        text='These verified work areas may proceed independently: '+'; '.join(expression(e) for e in group)
        def refs(expr):
            if expr.kind=='action':return {expr.ref}
            if expr.kind=='selected_option_of':return {a for o in branches[expr.ref].options for a in o.action_ids}
            return set().union(*(refs(c) for c in expr.children))
        for aid in set().union(*(refs(e) for e in group)):
            add(aid,'parallel_area',text,source.relationships.evidence_ids,'overlay-parallel:'+str(i))
    mode=document['configuration']['relationships']
    return {'mode':mode,'inline_by_action':inline if mode=='inline' else {},
            'map':{'labels':labels,'edges':document['edges'],'joins':document['joins'],'branches':document['branches'],
                   'parallel':document['parallel'],'parallel_areas':document['parallel_areas'],'stages':document['stages'],
                   'text_equivalent':list(dict.fromkeys(notes))} if mode=='map' else None,
            'essential_relationships_remain_in_instructions':True}


def render(source, content, config, constraints, compose_fn=compose):
    doc=compose_fn(source,content,config,constraints);g=source.graph
    stages={s.service_id:s for s in g.stages};actions={a.action_id:a for a in g.actions}
    for fact in doc['facts']:
        fact['source_context']=[{'content_id':c.content_id,'text':c.text,'evidence_ids':list(c.evidence_ids)} for c in g.content if fact['fact_id'] in c.fact_ids]
        fact['applicability_status']='structured_conditions' if fact.get('condition_ids') else 'consult_source_context'
    facts={f['id']:f for f in doc['facts']}
    reminders={}
    for a in doc['actions']:
        original=actions[a['id']]
        if a['recap']:reminders[a['id']]=a['recap']
        a['recap']=None
        a.update(service_id=original.service_id,agency=stages[original.service_id].agency,
                 condition_ids=list(original.applicability.condition_ids),source_content_ids=list(original.required_content_ids),
                 disclosure_available=bool(a['explanation_hidden']),wording_status=('provisional' if getattr(content,'origin',None)=='demo_mock' else 'published') if content else 'source_fallback')
        a['facts']=[facts[f['id']] for f in a['facts']]
    conditions={c.condition_id:c.text for c in g.conditions}
    doc['routes']=[{'branch_id':b.group_id,'selection':b.selection,'evidence_ids':list(b.evidence_ids),
                    'choice_is_not_eligibility_or_completion':True,'options':[{'option_id':o.option_id,'action_ids':list(o.action_ids),
                    'condition_ids':list(o.condition_ids),'conditions':[conditions[c] for c in o.condition_ids],
                    'label':' / '.join(conditions[c] for c in o.condition_ids) or ' / '.join(doc['map_labels'][a] for a in o.action_ids)} for o in b.options]} for b in g.branch_groups]
    doc['synthetic']=g.synthetic
    doc['source_kind']='fictional' if g.synthetic else 'bounded_official_source_snapshot'
    doc['conditions']=[c.model_dump(mode='json') for c in g.conditions]
    doc['provenance']=[p.model_dump(mode='json') for p in g.provenance]
    doc['requirements']={'documents':[f for f in doc['facts'] if f['fact']['kind']=='document'],
                         'fees':[f for f in doc['facts'] if f['fact']['kind']=='fee'],
                         'total':None,'no_total_reason':'Charges are scoped source facts; no total or alternative-route sum is inferred.',
                         'placement':'Always available outside explanation disclosure; stage facts are not action payments.'}
    doc['required_source_notes']=list(dict.fromkeys(doc['required_source_notes']))
    doc['relationship_aid']=relationship_aid(source,doc)
    doc['navigation']={}
    return doc,reminders


def interaction_projection(source, view, state):
    document=view['document'];nav=navigation(source,document,state)
    current=nav['active_action_id'];layers=ordering(source,state['routes']);allowed=eligible_ids(source.graph,state['routes'],require_choice=True)
    items=[];reason=None
    if document['configuration']['recap']=='on':
        if current is None or layers.get(current) is None:reason='no_active_verified_layer'
        elif nav['mode']=='overview' and state.get('viewport') is None:reason='awaiting_viewport_evidence'
        else:
            for aid,evidence in state['visited'].items():
                if aid not in allowed or aid==current or layers.get(aid) is None or layers[aid]>=layers[current]:continue
                if nav['mode']=='overview' and aid in state.get('viewport',[]):continue
                text=view['reminders'].get(aid)
                if text:items.append({'action_id':aid,'text':text,'evidence':evidence,'viewed_not_completed':True})
    else:reason='recap_off'
    return {'navigation':nav,'route_choices':state['routes'],'map_visible':state['map_visible'],
            'explanation_open_action_ids':state['explanation_open'], 'display_acknowledged_view_ids':state['displayed_views'],
            'recap':{'enabled':document['configuration']['recap']=='on','items':items,'empty_reason':reason if not items else None,
                     'label':'Earlier guidance viewed, not confirmed as done'},
            'event_count':state['sequence'],'completion_tracked':False}

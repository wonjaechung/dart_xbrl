import argparse
from lxml import etree
import pandas as pd


def parse_labels(label_file, lang='ko'):
    ns = {
        'link':  'http://www.xbrl.org/2003/linkbase',
        'xlink': 'http://www.w3.org/1999/xlink',
        'xml':   'http://www.w3.org/XML/1998/namespace'
    }
    tree = etree.parse(label_file)
    root = tree.getroot()
    
    locs = {}
    for loc in root.findall('.//link:loc', ns):
        loc_id = loc.get('{http://www.w3.org/1999/xlink}label')
        element = loc_id.split('#')[-1].split('_')[-1]
        locs[loc_id] = element
    
    labels = {}
    for lab in root.findall('.//link:label', ns):
        if lab.get('{http://www.w3.org/XML/1998/namespace}lang') == lang:
            labels[lab.get('{http://www.w3.org/1999/xlink}label')] = lab.text.strip() if lab.text else ''
    
    element_labels = {}
    for arc in root.findall('.//link:labelArc', ns):
        elem = locs.get(arc.get('{http://www.w3.org/1999/xlink}from'))
        text = labels.get(arc.get('{http://www.w3.org/1999/xlink}to'))
        if elem and text:
            element_labels[elem] = text
    return element_labels


def dissect_context_ref(ctx_ref):
    parts = ctx_ref.split('_')
    period_code = ''.join([c for c in parts[0] if not c.isdigit()])
    taxonomy    = parts[1] if len(parts) > 1 else None
    stmt_scope  = parts[2] if len(parts) > 2 else None
    
    scope_map = {
        'ConsolidatedAndSeparateFinancialStatements': '연결·별도 모두',
        'ConsolidatedFinancialStatementsOnly':        '연결만',
        'SeparateFinancialStatementsOnly':            '별도만'
    }
    return period_code, taxonomy, scope_map.get(stmt_scope, stmt_scope)


def parse_xbrl_full(xbrl_file, labko_file, laben_file):
    ns_inst = {
        'xbrli':   'http://www.xbrl.org/2003/instance',
        'xbrldi':  'http://xbrl.org/2006/xbrldi'
    }
    tree = etree.parse(xbrl_file)
    root = tree.getroot()

    # Contexts
    contexts = {}
    for ctx in root.findall('.//xbrli:context', ns_inst):
        cid = ctx.get('id')
        p   = ctx.find('xbrli:period', ns_inst)
        inst= p.find('xbrli:instant', ns_inst)
        date= inst.text if inst is not None else f"{p.find('xbrli:startDate', ns_inst).text} to {p.find('xbrli:endDate', ns_inst).text}"
        ent = ctx.find('xbrli:entity/xbrli:identifier', ns_inst).text
        scenario = {}
        for mem in ctx.findall('.//xbrldi:explicitMember', ns_inst):
            dim = mem.get('dimension').split(':')[-1]
            member = mem.text.split(':')[-1]
            scenario[dim] = member
        contexts[cid] = {'date': date, 'entity': ent, 'scenario': scenario}

    # Units
    units = {}
    for unit in root.findall('.//xbrli:unit', ns_inst):
        uid = unit.get('id')
        m   = unit.find('xbrli:measure', ns_inst)
        units[uid] = m.text if m is not None else None

    # Facts
    facts = []
    for el in root.iter():
        tag_ns = etree.QName(el).namespace
        if el.get('contextRef') and tag_ns not in ns_inst.values():
            facts.append({
                'name':       etree.QName(el).localname,
                'contextRef': el.get('contextRef'),
                'unitRef':    el.get('unitRef'),
                'decimals':   el.get('decimals'),
                'value':      el.text
            })

    df = pd.DataFrame(facts)
    df['period'] = df['contextRef'].map(lambda x: contexts[x]['date'])
    df['entity'] = df['contextRef'].map(lambda x: contexts[x]['entity'])
    df['unit']   = df['unitRef'].map(lambda x: units.get(x))

    ko_map = parse_labels(labko_file, lang='ko')
    en_map = parse_labels(laben_file, lang='en')
    df['label_ko'] = df['name'].map(lambda n: ko_map.get(n, n))
    df['label_en'] = df['name'].map(lambda n: en_map.get(n, n))

    meta = df['contextRef'].map(dissect_context_ref)
    df[['period_code','taxonomy','stmt_scope']] = pd.DataFrame(meta.tolist(), index=df.index)

    # Scenario members
    scenario_df = pd.json_normalize(df['contextRef'].map(lambda x: contexts[x]['scenario'])).fillna('None')
    df = pd.concat([df, scenario_df], axis=1)

    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XBRL Parsing Script")
    parser.add_argument("xbrl_file", help="Path to XBRL instance file")
    parser.add_argument("labko_file", help="Path to Korean labels linkbase")
    parser.add_argument("laben_file", help="Path to English labels linkbase")
    parser.add_argument("--output", default="parsed_xbrl.csv", help="Output CSV file")
    args = parser.parse_args()

    df = parse_xbrl_full(args.xbrl_file, args.labko_file, args.laben_file)
    df.to_csv(args.output, index=False)
    print(f"Parsed data saved to {args.output}")


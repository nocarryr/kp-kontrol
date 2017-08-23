import os
import argparse
import json

from kpkontrol.actions import GetAllParameters
from kpkontrol.objects import EnumParameter

def params_to_html(params):

    col_names = [
        'name', 'id', 'param_type', 'class_names', 'relations', 'persistence_type', 'register_type', 'enum_items',
    ]
    lines = [
        '<html>',
        '<head><style>',
        'table{border-spacing:1px;}',
        'td,th{border-style:solid;border-width:1px;font-size:.8em;}',
        '</style></head>',
        '<body>',
        '<table>',
        '<thead><tr>'
    ]
    for c in col_names:
        lines.append('<th>{}</th>'.format(c))
    lines.extend([
        '</tr></thead>',
        '<tbody>',
    ])
    for param_types in params['by_type'].values():
        for param in param_types.values():
            lines.append('<tr>')
            for c in col_names:
                if c == 'enum_items':
                    continue
                lines.append('<td>{}</td>'.format(getattr(param, c)))
            if isinstance(param, EnumParameter):
                rtag_closed = False
                for key, item in param.enum_items_by_value.items():
                    if not rtag_closed:
                        lines.append('<td>{}: {}</td>'.format(key, item.name))
                        lines.append('</tr>')
                        rtag_closed = True
                    else:
                        cols = ['<td></td>']*(len(col_names)-1)
                        cols.append('<td>{}: {}</td>'.format(key, item.name))
                        lines.append('<tr>{}</tr>'.format(''.join(cols)))
            else:
                lines.append('</tr>')
    lines.extend([
        '</tbody></table>',
        '</body></html>',
    ])
    s = '\n'.join(lines)
    return s

def params_to_json(params, **kwargs):
    def serialize_obj(o):
        d = {}
        for attr in o.attribute_names_:
            if attr == 'enum_items_by_value':
                continue

            val = getattr(o, attr)
            if attr == 'enum_items':
                d['enum_items'] = {}
                for key, item in o.enum_items.items():
                    d['enum_items'][key] = serialize_obj(item)
            else:
                d[attr] = val
        return d

    data = {}
    for param_type, _params in params['by_type'].items():
        data[param_type] = {}
        for param in _params.values():
            data[param_type][param.id] = serialize_obj(param)

    return json.dumps(data, **kwargs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', dest='host', required=True, help='Device host address')
    p.add_argument('-f', '--format', dest='format', default='html', choices=['html', 'json'])
    p.add_argument('--compact', dest='compact', action='store_true', help='Compact JSON format')
    p.add_argument('outfile')
    args = p.parse_args()

    params = GetAllParameters(args.host)()

    if args.format == 'html':
        s = params_to_html(params)
    elif args.format == 'json':
        json_kw = {}
        if not args.compact:
            json_kw['indent'] = 2
        s = params_to_json(params, **json_kw)

    with open(args.outfile, 'w') as f:
        f.write(s)

if __name__ == '__main__':
    main()

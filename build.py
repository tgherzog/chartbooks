
"""
This script builds a chart book of country sheets using an indicator schema specified in a YAML file
and pulling data from World Bank APIs

Usage:
  build.py [--debug] [--config=CONFIG] FILE

Options:
  --config=CONFIG    Config file in yaml format [default: config.yaml]

  --debug, -v        Debug mode

"""

import yaml
import xlsxwriter
import wbgapi as wb
from pprint import pprint
import logging
import sys
from docopt import docopt

docopts = docopt(__doc__)
_formats = {}

def format(key, wb=None, attrs={}, precision=None):
    '''Lookup and optionally define a new format in the workbook

       key:       string to identify the format
       wb:        Workbook object - required if the format hasn't been defined yet
       attrs:     attributes for the format, if not yet defined
       precision: shortcut for creating number formats

       Returns: a Format object
    '''

    if key in _formats:
        return _formats[key]

    if precision is not None:
        attrs['num_format'] = '#,##0'
        if precision:
            attrs['num_format'] += '.' + ('0' * precision)
            attrs['align'] = 'right'

    logging.debug('Adding format {}: {}'.format(key, str(attrs)))
    _formats[key] = wb.add_format(attrs)
    return _formats[key]

def load_config(path='config.yaml'):
    '''Load and normalize config for the session
    '''

    config = yaml.safe_load(open(path, 'r'))

    def normalize(i):

        ilist = []
        if i is None:
            return ilist

        for elem in i:
            if type(elem) is str:
                elem = {'id': elem}

            # this is an atypical way to fetch attributes but only the old-style endpoints give us precision
            attrs = list(wb.fetch('country/{}/indicator/{}'.format('USA', elem['id']), {'mrv': 1}))[0]

            if 'name' not in elem:
                elem['name'] = attrs['indicator']['value']

            if 'source' not in elem:
                elem['source'] = 2 # default to WDI

            if 'multiplier' not in elem:
                elem['multiplier'] = 1

            if 'precision' not in elem:
                elem['precision'] = attrs['decimal']

            ilist.append(elem)

        return ilist
                
    config['options'] = config.get('options', {})
    config['yearly'] = normalize(config.get('yearly', []))
    config['quarterly'] = normalize(config.get('quarterly', []))
    config['monthly'] = normalize(config.get('monthly', []))

    if not config.get('economies'):
        # if economies is unspecified, get the full WDI list with option to include aggregates 
        config['economies'] = wb.economy.DataFrame(skipAggs=not config['options'].get('aggregates',False)).index

    return config

if docopts['--debug']:
    logging.basicConfig(level=logging.DEBUG)

config = load_config(docopts['--config'])

sheet_list = {}
for row in wb.economy.list(config['economies']):
    sheet_list[row['id']] = row['value']

xls = xlsxwriter.Workbook(docopts['FILE'])
toc = xls.add_worksheet('Overview')
toc.set_column(0, 0, width=40)
tocRow = 1

format('bold', xls, {'bold': 1})
format('colhdr', xls, {'bg_color': '#E0E0E0', 'bold': 1, 'text_wrap': 1})
format('colhdr2', xls, {'bg_color': '#E0E0E0', 'bold': 1, 'text_wrap': 1, 'align': 'right'})
format('ralign', xls, {'align': 'right'})

if docopts['--debug']:
    print('Parsed Config Info:', file=sys.stderr)
    pprint(config, stream=sys.stderr)

for cets,v in sheet_list.items():
    country = xls.add_worksheet(v)

    country.write(0, 0, v, format('bold')) # country name in R1C1
    toc.write_url(tocRow, 0, "internal:'{}'!A1".format(v), string=v)
    tocRow += 1

    country.set_row(1, height=32, cell_format=format('colhdr'))

    df = None
    for source in set(map(lambda x: x['source'], config['yearly'])):
        series = {row['id']:row for row in config['yearly'] if row.get('source',0) == source}
        df2 = wb.data.DataFrame(series.keys(), cets, db=source, columns='series')
        if df is None:
            df = df2
        else:
            df = df.join(df2, how='outer')

    row = 1
    col = 0
    country.write(row, col, 'Year')
    country.write_column(row+1, col, df.index)
    col += 1
    for elem in config['yearly']:
        if elem['id'] in df.columns:
            # NB: column alignment seems to get ignored for cells that have values, so this
            # needs to set alignment at the cell level, not the column level which would be more convenient
            country.set_column(col, col, width=13)
            country.write(row, col, elem['name'], format('colhdr2'))
            country.write_column(row+1, col,
                (df[elem['id']] * elem['multiplier']).fillna(''),
                cell_format=format('n{}'.format(elem['precision']), xls, precision=elem['precision']))

            col += 1

xls.close()

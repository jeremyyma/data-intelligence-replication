
import sdi_utils.gensolution as gs
import subprocess
import os

import io
import logging
import pandas as pd

import sdi_utils.textfield_parser as tfp


try:
    api
except NameError:
    class api:

        queue = list()

        class Message:
            def __init__(self,body = None,attributes = ""):
                self.body = body
                self.attributes = attributes

        def send(port,msg) :
            if port == outports[1]['name'] :
                api.queue.append(msg)

        class config:
            ## Meta data
            config_params = dict()
            tags = {'sdi_utils': ''}
            version = "0.0.1"
            operator_name = 'repl_table_csv'
            operator_description = "table to csv"
            operator_description_long = "Converts table to csv stream."
            add_readme = dict()
            debug_mode = True

            drop_header = False
            config_params['drop_header'] = {'title': 'Drop header',
                                           'description': 'Drop header (not only for the first run).',
                                           'type': 'boolean'}

            only_header = False
            config_params['only_header'] = {'title': 'Only header',
                                           'description': 'Only header (for preparation purpose).',
                                           'type': 'boolean'}

            drop_columns = 'None'
            config_params['drop_columns'] = {'title': 'Drop Columns',
                                           'description': 'List of columns to drop.',
                                           'type': 'string'}

        logger = logging.getLogger(name=config.operator_name)

# catching logger messages for separate output
log_stream = io.StringIO()
sh = logging.StreamHandler(stream=log_stream)
sh.setFormatter(logging.Formatter('%(asctime)s |  %(levelname)s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
api.logger.addHandler(sh)


list_headers = set()

def process(msg):
    global list_dicts

    att = dict(msg.attributes)
    att['operator'] = 'repl_table_csv'

    header = [c["name"] for c in msg.attributes['table']['columns']]
    df = pd.DataFrame(msg.body, columns=header)

    att['data_outcome'] = True

    drop_columns = tfp.read_list(api.config.drop_columns)
    if drop_columns:
        api.logger.info('Drop columns: {}'.format(drop_columns))
        df = df.drop(columns=drop_columns)

    if df.shape[0] == 0 and not api.config.only_header:
        att['data_outcome'] = False
        api.send(outports[2]['name'], api.Message(attributes=att, body=att['data_outcome']))
        api.logger.info('No data received, msg to port error_status sent.')
        api.send(outports[0]['name'], log_stream.getvalue())
        return 0

    if api.config.only_header:
        att['data_outcome'] = False  # Only one call necessary, but should send data for writing

    # always sort the columns alphabetically because DB columns do not have an order
    df = df[sorted(df.columns)]

    if api.config.drop_header and api.config.only_header:
        err_stat = "Contradicting configuration - Drop header: {}  Only header: {}".format(api.config.drop_header,
                                                                                           api.config.only_header)
        raise ValueError(err_stat)

    if api.config.only_header:
        df = df.head(n=0)
        data_str = df.to_csv(index=False)
    # drop headers if it is part of multiple calls (key: table name and cols)
    elif api.config.drop_header:
        data_str = df.to_csv(index=False, header=False, date_format='%Y%m%d %H:%M:%S')
    else:
        if 'base_table' in att:
            col_str = att['base_table'] + '-' + ' '.join(df.columns.tolist())
        else:
            col_str = att['table_name'] + '-' + ' '.join(df.columns.tolist())
        if col_str in list_headers:
            data_str = df.to_csv(index=False, header=False, date_format='%Y%m%d %H:%M:%S')
        else:
            data_str = df.to_csv(index=False, date_format='%Y%m%d %H:%M:%S')
            list_headers.add(col_str)

    att["file"] = {"connection": {"configurationType": "Connection Management", "connectionID": "unspecified"}, \
                   "path": "open", "size": 0}

    api.logger.info('CSV-table: {}.{} ({} - {})'.format(att['schema_name'], att['table_name'], df.shape[0], df.shape[1]))
    api.logger.debug('First to rows: {}'.format(df.head(2)))

    msg = api.Message(attributes=att, body=data_str)
    api.send(outports[1]['name'], msg)

    log = log_stream.getvalue()
    if len(log) > 0:
        api.send(outports[0]['name'], log_stream.getvalue())

inports = [{'name': 'data', 'type': 'message.table',"description":"Input message with table"}]
outports = [{'name': 'log', 'type': 'string',"description":"Logging data"}, \
            {'name': 'csv', 'type': 'message.file',"description":"Output data as csv"},\
            {'name': 'error', 'type': 'message',"description":"Error status"}]


#api.set_port_callback(inports[0]['name'], process)

def test_operator() :
    #api.config.drop_header = False
    #api.config.only_header = True

    attributes = {"table":{"columns":[{"class":"string","name":"header1","nullable":True,"size":80,"type":{"hana":"NVARCHAR"}},
                                      {"class":"string","name":"header2","nullable":True,"size":3,"type":{"hana":"NVARCHAR"}},
                                      {"class":"string","name":"header3","nullable":True,"size":10,"type":{"hana":"NVARCHAR"}}],
                           "name":"test.table","version":1},
                  'base_table':'TABLE','schema_name':'schema','table_name':'table'}
    table = [ [(j*3 + i) for i in range(0,3)] for j in range (0,5)]
    msg = api.Message(attributes=attributes, body=table)
    print(table)
    process(msg)
    process(msg)
    process(msg)

    for m in api.queue :
        print(m.body)



if __name__ == '__main__':
    test_operator()
    if True :
        basename = os.path.basename(__file__[:-3])
        package_name = os.path.basename(os.path.dirname(os.path.dirname(__file__)))
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        solution_name = '{}_{}.zip'.format(basename,api.config.version)
        package_name_ver = '{}_{}'.format(package_name,api.config.version)

        solution_dir = os.path.join(project_dir,'solution/operators',package_name_ver)
        solution_file = os.path.join(project_dir,'solution/operators',solution_name)

        # rm solution directory
        subprocess.run(["rm", '-r',solution_dir])

        # create solution directory with generated operator files
        gs.gensolution(os.path.realpath(__file__), api.config, inports, outports)

        # Bundle solution directory with generated operator files
        subprocess.run(["vctl", "solution", "bundle", solution_dir, "-t",solution_file])

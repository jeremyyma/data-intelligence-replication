import sdi_utils.gensolution as gs
import subprocess
import os

import io
import pandas as pd
import logging

pd.set_option('expand_frame_repr', True)
pd.set_option('display.max_columns', 100)
pd.set_option('display.width', 200)
try:
    api
except NameError:
    class api:

        queue = list()
        queue_sql = list()
        class Message:
            def __init__(self,body = None,attributes = ""):
                self.body = body
                self.attributes = attributes

        def send(port,msg) :
            if port == outports[1]['name'] :
                api.queue.append(msg)
            elif port == outports[2]['name'] :
                api.queue_sql.append(msg)

        class config:
            ## Meta data
            config_params = dict()
            tags = {'sdi_utils':''}
            version = "0.0.1"
            operator_name = 'repl_merge_files'
            operator_description = "Merge Files"
            operator_description_long = "Merges all update files with the target file."
            add_readme = dict()


        format = '%(asctime)s |  %(levelname)s | %(name)s | %(message)s'
        logging.basicConfig(level=logging.DEBUG, format=format, datefmt='%H:%M:%S')
        logger = logging.getLogger(name=config.operator_name)



# catching logger messages for separate output
log_stream = io.StringIO()
sh = logging.StreamHandler(stream=log_stream)
sh.setFormatter(logging.Formatter('%(asctime)s |  %(levelname)s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
api.logger.addHandler(sh)

df = pd.DataFrame()


def process(msg):

    global df

    att = dict(msg.attributes)
    att['operator'] = 'repl_merge_files'

    csv_io = io.BytesIO(msg.body)
    if att['target_file'] :
        df = pd.read_csv(csv_io)
    else :
        df = df.append(pd.read_csv(csv_io), ignore_index=True)

    api.logger.debug('Update file: {} ({})'.format(df.shape[0],att['file']['path']))

    if att['message.last_update_file']:
        api.logger.debug('Last Update file - merge')
        #  cases:
        #  I,U: normal, U,I : should not happen, sth went wrong with original table (no test)
        #  I,D: normal, D,I : either sth went wrong in the repl. table or new record (no test)
        #  U,D: normal, D,U : should not happen, sth went wrong with original table (no test)

        # keep only the most updated records irrespective of change type I,U,D
        gdf = df.groupby(by = att['current_primary_keys'])['DIREPL_UPDATED'].max().reset_index()
        keys = att['current_primary_keys'] + ['DIREPL_UPDATED']
        df = pd.merge(gdf, df, on=keys, how='inner')

        # remove D-type records
        df = df.loc[~(df['DIREPL_TYPE']=='D')]

        # prepare for saving
        df = df[sorted(df.columns)]
        if df.empty :
            raise ValueError('DataFrame is empty - Avoiding to create empty file!')

        csv = df.to_csv(index=False)
        att['file']['path'] = os.path.join(att['current_file']['dir'], att['current_file']['base_file'])
        api.send(outports[1]['name'],api.Message(attributes=att, body=csv))

        # checksum
        repos_table = att['table_repository'] if 'table_repository' in att else ''
        checksum_col = att['checksum_col'] if 'checksum_col' in att else ''
        if not repos_table or not checksum_col :
            api.logger.warning('Checksum not setup checksum_col: {}  repository table: {}'.format(checksum_col,repos_table))
        else :
            checksum = df[checksum_col].sum()
            num_rows = df.shape[0]

            table = att['current_file']['schema_name'] + '.' +  att['current_file']['table_name']
            sql = 'UPDATE {repos_table} SET \"FILE_CHECKSUM\" = {cs}, \"FILE_ROWS\" = {nr}, \"FILE_UPDATED\" = CURRENT_UTCTIMESTAMP ' \
            ' WHERE \"TABLE_NAME\"  = \'{table}\' '.format(cs=checksum,nr = num_rows,repos_table = repos_table,table = table)
            api.logger.info("SQL statement for consistency update: {}".format(sql))
            att['sql'] = sql
            api.send(outports[3]['name'],api.Message(attributes=att, body=sql))
    else:
        api.send(outports[2]['name'], api.Message(attributes=att, body=''))

    log = log_stream.getvalue()
    if len(log)>0 :
        api.send(outports[0]['name'], log_stream.getvalue())

inports = [{'name': 'data', 'type': 'message.file', "description": "Input Data as csv"}]
outports = [{'name': 'log', 'type': 'string', "description": "Logging data"}, \
            {'name': 'csv', 'type': 'message.file', "description": "Output data as csv"},
            {'name': 'next', 'type': 'message.file', "description": "Next file"},
            {'name': 'consistency', 'type': 'message', "description": "sql consistency update"}]


# api.set_port_callback(inports[0]['name'], process)


def test_operator() :
    att = {'operator': 'collect_files', 'file': {'path': '/adbd/abd.csv'},'current_primary_keys':['INDEX'],\
           'message.last_update_file':False,'checksum_col':'INDEX','table_repository':'REPLICATION.TEST_TABLES_REPOS', 'schema_name':'REPLICATION',\
           'table_name':'TEST_TABLE_0','target_file':True}
    att['current_file'] = {
            "dir": "/replication/REPLICATION/TEST_TABLE_17",
            "update_files": [
                "12345_TEST_TABLE_17.csv"
            ],
            "base_file": "TEST_TABLE_17.csv",
            "schema_name": "REPLICATION",
            "table_name": "TEST_TABLE_17",
            "primary_key_file": "TEST_TABLE_17_primary_keys.csv",
            "consistency_file": "",
            "misc": []
        }
    csv1 = r'''DIREPL_TYPE,DIREPL_UPDATED,INDEX,NUMBER
I,2020-07-27T09:38:46.038Z,0,0
I,2020-07-27T09:38:46.038Z,1,1
I,2020-07-27T09:38:46.038Z,2,2
I,2020-07-27T09:38:47.038Z,3,3
I,2020-07-27T09:38:48.038Z,4,4
I,2020-07-27T09:38:49.657Z,5,5'''
    csv1 = str.encode(csv1)
    csv2 = r'''DIREPL_TYPE,DIREPL_UPDATED,INDEX,NUMBER
U,2020-07-27T09:39:06.657Z,6,6
U,2020-07-27T09:39:09.657Z,7,7
U,2020-07-27T09:39:06.657Z,8,0
U,2020-07-27T09:39:06.657Z,9,2
U,2020-07-27T09:39:06.657Z,10,3'''
    csv2 = str.encode(csv2)
    csv3 = r'''DIREPL_TYPE,DIREPL_UPDATED,INDEX,NUMBER
    U,2020-07-27T09:49:06.657Z,11,16
    U,2020-07-27T09:49:09.657Z,12,17
    U,2020-07-27T09:49:06.657Z,13,10
    U,2020-07-27T09:49:06.657Z,14,12
    U,2020-07-27T09:49:06.657Z,15,13'''
    csv3 = str.encode(csv3)

    msg = api.Message(attributes=att,body=csv1)
    process(msg)

    att['file']['path'] = '/adbd/111111_abcd.csv'
    att['target_file']= False
    msg = api.Message(attributes=att, body=csv2)
    process(msg)

    att['file']['path'] = '/adbd/222222_abcd.csv'
    att['message.last_update_file'] =  True
    msg = api.Message(attributes=att, body=csv3)
    process(msg)


    for q in api.queue :
        print(q.body)

    for q in api.queue_sql :
        print(q.body)


if __name__ == '__main__':
    test_operator()
    if True :
        basename = os.path.basename(__file__[:-3])
        package_name = os.path.basename(os.path.dirname(os.path.dirname(__file__)))
        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        solution_name = '{}_{}.zip'.format(basename, api.config.version)
        package_name_ver = '{}_{}'.format(package_name, api.config.version)

        solution_dir = os.path.join(project_dir, 'solution/operators', package_name_ver)
        solution_file = os.path.join(project_dir, 'solution/operators', solution_name)

        # rm solution directory
        subprocess.run(["rm", '-r', solution_dir])

        # create solution directory with generated operator files
        gs.gensolution(os.path.realpath(__file__), api.config, inports, outports)

        # Bundle solution directory with generated operator files
        subprocess.run(["vctl", "solution", "bundle", solution_dir, "-t", solution_file])

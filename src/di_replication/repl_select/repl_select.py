import sdi_utils.gensolution as gs
import os
import subprocess

import logging
import io


try:
    api
except NameError:
    class api:

        queue = list()

        class Message:
            def __init__(self, body=None, attributes=""):
                self.body = body
                self.attributes = attributes

        def send(port, msg):
            if port == outports[1]['name']:
                api.queue.append(msg)

        class config:
            ## Meta data
            config_params = dict()
            version = '0.0.1'
            tags = {}
            operator_name = 'repl_select'
            operator_description = "Repl. Select"

            operator_description_long = "Creates SELECT SQL-statement for replication."
            add_readme = dict()
            add_readme["References"] = ""


        format = '%(asctime)s |  %(levelname)s | %(name)s | %(message)s'
        logging.basicConfig(level=logging.DEBUG, format=format, datefmt='%H:%M:%S')
        logger = logging.getLogger(name=config.operator_name)



# catching logger messages for separate output
log_stream = io.StringIO()
sh = logging.StreamHandler(stream=log_stream)
sh.setFormatter(logging.Formatter('%(asctime)s |  %(levelname)s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
api.logger.addHandler(sh)

def process(msg):

    att = dict(msg.attributes)
    att['operator'] = 'repl_select'

    api.logger.info("Process started")
    api.logger.debug('Attributes: {} - {}'.format(str(msg.attributes),str(att)))

    sql = 'SELECT * FROM {table} WHERE \"DIREPL_STATUS\" = \'B\' AND  \"DIREPL_PID\" = \'{pid}\' '.\
        format(table=att['replication_table'],pid= att['pid'])
    att['sql'] = sql
    msg = api.Message(attributes=att,body = sql)

    api.logger.info('SELECT statement: {}'.format(sql))

    api.send(outports[1]['name'], msg)

    log = log_stream.getvalue()
    if len(log) > 0 :
        api.send(outports[0]['name'], log )


inports = [{'name': 'trigger', 'type': 'message.table', "description": "Input data"}]
outports = [{'name': 'log', 'type': 'string', "description": "Logging data"}, \
            {'name': 'msg', 'type': 'message', "description": "message with sql statement"}]

#api.set_port_callback(inports[0]['name'], process)

def test_operator():

    msg = api.Message(attributes={'pid': 123123213, 'replication_table':'REPL_TABLE','base_table':'REPL_TABLE','latency':30,'data_outcome':True},body='')
    process(msg)

    for m in api.queue:
        print('Attributes: \n{}'.format(m.attributes))
        print('Body: \n{}'.format(m.body))


if __name__ == '__main__':
    test_operator()
    if True:
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



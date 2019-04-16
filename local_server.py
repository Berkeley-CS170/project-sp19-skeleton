import sys
# Python 3 verification
if sys.version_info < (3, 0):
    print('Please use Python 3.')
    sys.exit(1)

import argparse
from flask import Flask, jsonify, request
import json
import networkx as nx
import os
import random

app = Flask(__name__)

data = None
instance_name = None

@app.route('/api/start', methods=['POST'])
def start():
    # Error handling
    global data
    if data:
        return abort(403, 'Active rescue',
            "https://guavabot.cs170.org/api/errors/#active-rescue")

    # pick a random file_name
    candidates = [file for file in os.listdir('test_graphs') \
        if file.endswith('.json')]
    file_name = random.choice(candidates)
    # if we can find the graph file name, then use that instead.
    if instance_name:
        arg_file = instance_name.rsplit('_', 1)[0] + '.json'
        if arg_file in candidates:
            file_name = arg_file

    with open('test_graphs/{}'.format(file_name), 'r') as f:
        graph_data = json.load(f)
    instance = random.choice(graph_data['instances'])
    # if we can find the instance name, then use that instead.
    if instance_name:
        for _instance in graph_data['instances']:
            if _instance['instanceName'].lower() == instance_name.lower():
                instance = _instance
                break

    print('Using instance {}.'.format(instance['instanceName']),
        file=sys.stderr)

    data = {
        'city': graph_data['city'],
        'home': instance['home'],
        'k': graph_data['students'],
        'l': len(instance['bots']),
        's': graph_data['scoutTime'],
        'time': 0,
    }
    # only send part of the data to the client
    ret_data = jsonify(data)

    data['G'] = nx.Graph()
    data['G'].add_weighted_edges_from(graph_data['edgelist'])
    n = len(data['G'])

    data['bots'] = [0] * (n + 1)
    for location in instance['bots']:
        data['bots'][location] += 1

    # correct[student][vertex] represents whether student will respond
    #   correctly to a scout on vertex.
    data['correct'] = [[True] * (n + 1) \
        for _ in range(graph_data['students'] + 1)]
    for student in range(graph_data['students']):
        vertices = instance['studentErrors'][student]
        for vertex in vertices:
            data['correct'][student + 1][vertex] = False

    # locations that may not be scouted for each student
    data['forbidden_scouts'] = [set() for _ in range(data['k'] + 1)]
    return ret_data

@app.route('/api/scout', methods=['POST'])
def scout():
    # Error handling
    if 'vertex' not in request.form \
            or 'students' not in request.form:
        return abort(403, 'Malformed request',
            "https://guavabot.cs170.org/api/errors/#malformed-request")

    # Input data processing
    vertex = int(request.form['vertex'])
    students = [int(student) for student in request.form.getlist('students')]
    # Error handling
    if not data:
        return abort(403, 'No active rescue',
            "https://guavabot.cs170.org/api/errors/#no-active-rescue")
    if not data['G'].has_node(vertex):
        return abort(403, 'Malformed scout',
            "https://guavabot.cs170.org/api/errors/#malformed-scout")
    if vertex == data['home']:
        return abort(403, 'Scout not allowed',
            "https://guavabot.cs170.org/api/errors/#scout-not-allowed")        
    for student in students:
        if not isinstance(student, int):
            return abort(403, 'Malformed request',
                "https://guavabot.cs170.org/api/errors/#malformed-request")            
        if student <= 0 or student > data['k']:
            return abort(403, 'Malformed scout',
                "https://guavabot.cs170.org/api/errors/#malformed-scout")
        if vertex in data['forbidden_scouts'][student]:
            return abort(403, 'Scout not allowed',
                "https://guavabot.cs170.org/api/errors/#scout-not-allowed")

    ret_data = {'reports': {}}
    for student in students:
        # on success
        if data['correct'][student][vertex]:
            ret_data['reports'][student] = data['bots'][vertex] > 0
            # vertex cannot be scouted by student anymore
            data['forbidden_scouts'][student].add(vertex)
        else:
            ret_data['reports'][student] = not (data['bots'][vertex] > 0)

    data['time'] += data['s'] * len(students)
    ret_data['time'] = data['time']
    return jsonify(ret_data)

@app.route('/api/remote', methods=['POST'])
def remote():
    # Error handling
    if 'from_vertex' not in request.form \
            or 'to_vertex' not in request.form:
        return abort(403, 'Malformed request',
            "https://guavabot.cs170.org/api/errors/#malformed-request")

    # Input data processing
    frum = int(request.form['from_vertex'])
    to = int(request.form['to_vertex'])
    # Error handling
    if not data:
        return abort(403, 'No active rescue',
            "https://guavabot.cs170.org/api/errors/#no-active-rescue")
    if frum == to \
            or not data['G'].has_node(frum) \
            or not data['G'].has_node(to) \
            or not data['G'].has_edge(frum, to):
        return abort(403, 'Malformed remote',
            "https://guavabot.cs170.org/api/errors/#malformed-remote")

    ret_data = {}
    ret_data['bots_remoted'] = data['bots'][frum]
    data['bots'][frum] = 0
    data['bots'][to] += ret_data['bots_remoted']

    for student in range(data['k']):
        data['forbidden_scouts'][student].add(frum)
    if ret_data['bots_remoted'] != 0:
        for student in range(data['k']):
            data['forbidden_scouts'][student].add(to)

    data['time'] += data['G'][frum][to]['weight']
    ret_data['time'] = data['time']
    return jsonify(ret_data)

@app.route('/api/end', methods=['POST'])
def end():
    # Error handling
    global data
    if not data:
        return abort(403, 'No active rescue',
            "https://guavabot.cs170.org/api/errors/#no-active-rescue")

    # some constant
    alpha = 20000
    home = data['home']
    score = 100 / (data['l'] + 1) * \
        (data['bots'][home] + alpha / (alpha + data['time']))

    ret_data = {
        'score': score,
    }
    data = None
    return jsonify(ret_data)

@app.route('/api/score', methods=['POST'])
def score():
    ret_data = {
        'submit_token': 'N/A, local run',
        'completed': 0,
        'remaining': 0,
    }
    return jsonify(ret_data)

def abort(status_code, error, documentation_url):
    response = jsonify({
        'error': error,
        'documentation_url': documentation_url,
    })
    response.status_code = status_code
    return response

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Guavabot local server: move all bots home!')
    parser.add_argument('--instance', dest='instance_name', default=None,
        help='The local instance to always serve.')
    args = parser.parse_args()

    if args.instance_name and args.instance_name.endswith('.json'):
        print('The instance name should not include .json.')
        sys.exit()

    instance_name = args.instance_name

    app.run(debug=True)

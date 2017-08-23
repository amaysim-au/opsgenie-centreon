#!/usr/bin/env python3
import os
import sys
import logging
from bs4 import BeautifulSoup
import requests
import aws_lambda_logging
import json
import re


def get_token(text):
    soup = BeautifulSoup(text, 'html.parser')
    inputs = soup.find_all('input')
    for input in inputs:
        if input['name'] == 'centreon_token':
            return input['value']


def get_login(url, useralias, password):
    r = requests.get(url + 'index.php', timeout=5)
    token = get_token(r.text)
    jar = r.cookies
    data = {}
    data = {'useralias': useralias,
            'password': password,
            'submitLogin': 'Connect',
            'centreon_token': token}
    r = requests.post(url + 'index.php', data=data, cookies=jar, timeout=5)
    logging.debug(json.dumps({'cookies': jar}))
    if useralias not in r.text:
        raise Exception("Failed to log in.")
    else:
        logging.info(json.dumps({'action': 'logged in'}))
    return jar


def logout(url, jar):
    r = requests(url + 'index.php?disconnect=1', timeout=5)
    logging.info(json.dumps({'action': 'logged out'}))


def ack_service(jar, url, service, host, useralias):
    fullurl = '{url}main.php?p=20201&o=svcak&cmd=15&host_name={host}&service_description={service}&en=1'.format(
        url=url, host=host, service=service)
    r = requests.get(fullurl, cookies=jar, timeout=5)
    logging.debug(json.dumps(r.text))

    token = get_token(r.text)

    logging.debug(json.dumps({'token': token}))

    data = {}
    data = {'comment': "Automated acknowledgement",
            'force_check': '1',
            'submit': 'Add',
            'host_name': host,
            'service_description': service,
            'author': useralias,
            'cmd': '15',
            'p': '20201',
            'en': '1',
            'centreon_token': token,
            'o': 'svcd'}

    logging.debug(json.dumps({"action": "post", "data": data}))
    logging.info(json.dumps({"action": "acknowledgement", "host": host, "service": service}))
    r = requests.post(
        '{url}main.php?p=20201&host_name={host}&service_description={service}'.format(
            url=url, host=host, service=service), data=data, cookies=jar, timeout=5)
    if useralias not in r.text:
        raise Exception("Failed to log in.")
    return(r)


def ack_host(jar, url, host, useralias):
    r = requests.get(
        '{url}main.php?p=20202&o=hak&cmd=14&host_name={host}&en=1'.format(
            url=url, host=host), cookies=jar, timeout=5)
    logging.debug(json.dumps({'text': r.text}))

    token = get_token(r.text)

    logging.debug(json.dumps({'token': token}))

    data = {}
    data = {'comment': "Automated acknowledgement",
            'persistent': '1',
            'sticky': '1',
            'submit': 'Add',
            'host_name': host,
            'author': useralias,
            'cmd': '14',
            'p': '20202',
            'en': '1',
            'centreon_token': token,
            'o': 'hd'}

    logging.debug(json.dumps({"action": "post", "data": data}))
    logging.info(json.dumps({"action": "acknowledgement", "host": host}))
    r = requests.post(
        '{url}main.php?p=20202&host_name={host}'.format(
            url=url, host=host), data=data, cookies=jar, timeout=5)
    return(r)


def handler(event, context):
    loglevel = os.environ.get('LOGLEVEL', 'INFO')
    aws_lambda_logging.setup(level=loglevel)
    logging.debug(json.dumps({'event': event}))
    try:
        logging.info(json.dumps({'sns': event['Records'][0]['Sns']['Message']}))
    except:
        raise Exception("Could not parse SNS payload.")

    url = os.environ['CENTREON_URL']
    useralias = os.environ['CENTREON_USERALIAS']
    password = os.environ['CENTREON_PASSWORD']

    action = ""
    try:
        action = json.loads(event['Records'][0]['Sns']['Message'])['action']
        logging.info(json.dumps({'sns_action': action}))
    except Exception as e:
        logging.critical(json.dumps({'action': 'extract action', 'status': 'failed', 'error': e}))

    message = ""
    try:
        message = json.loads(event['Records'][0]['Sns']['Message'])[
            'alert']['message']
    except Exception as e:
        logging.critical(json.dumps({'action': 'extract message', 'status': 'failed', 'error': e}))

    host = ""
    service = ""
    if '/' in message:
        try:
            host = re.search('Centreon: (.*)/', message).group(1)
            service = re.search('Centreon: .*/(.*) is', message).group(1)
            logging.debug('host: {host}, service: {service}'.format(
                host=host, service=service))
        except Exception as e:
            logging.critical(json.dumps({'action': 'extract service', 'status': 'failed', 'error': e}))
    else:
        try:
            host = re.search('Centreon: (.*) is', message).group(1)
            logging.debug('host: {host}'.format(host=host))
        except Exception as e:
            logging.critical(json.dumps({'action': 'extract host', 'status': 'failed', 'error': e}))

    if action in ['Close', 'Acknowledge']:
        logging.info(json.dumps({'action': 'submitting acknowledgement'}))
        if service:
            try:
                jar = get_login(url, useralias, password)
                ack_service(jar, url, service, host, useralias)
            except Exception as e:
                logging.critical(json.dumps({'action': 'submit service acknowedgement', 'status': 'failed', 'error': e, 'host': host, 'service': service}))
                return {
                    "statusCode": 503,
                    "body": 'Failed to submit service acknowledgement: {}'.format(e)
                }
        else:
            try:
                jar = get_login(url, useralias, password)
                ack_host(jar, url, host, useralias)
            except Exception as e:
                logging.critical(json.dumps({'action': 'submit service acknowedgement', 'status': 'failed', 'error': e, 'host': host}))
                return {
                    "statusCode": 503,
                    "body": 'Failed to submit host acknowledgement: {}'.format(e)
                }
    else:
        logging.info(json.dumps({'action': 'nothing'}))

    response = {
        "statusCode": 200,
        "body": 'OK'
    }
    return response


def local_test():
    url = os.environ['CENTREON_URL']
    useralias = os.environ['CENTREON_USERALIAS']
    password = os.environ['CENTREON_PASSWORD']
    service = 'testservice'
    host = 'testhost'
    jar = get_login(url, useralias, password)
    ack_service(jar, url, service, host, useralias)
    ack_host(jar, url, host, useralias)


def test_connectivity(event, context):
    loglevel = os.environ.get('LOGLEVEL', 'DEBUG')
    aws_lambda_logging.setup(level=loglevel)
    logging.debug(json.dumps({'event': event}))

    url = os.environ['CENTREON_URL']
    useralias = os.environ['CENTREON_USERALIAS']
    password = os.environ['CENTREON_PASSWORD']

    jar = get_login(url, useralias, password)
    logout(url, jar)
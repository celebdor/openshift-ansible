#!/usr/bin/env python
"""
This is an Ansible dynamic inventory for OpenStack.

It requires your OpenStack credentials to be set in clouds.yaml or your shell
environment.

"""

from __future__ import print_function

from collections import defaultdict

import json
import shade


def build_inventory():
    '''Build the dynamic inventory.'''
    cloud = shade.openstack_cloud()

    inventory = {}

    # TODO(shadower): filter the servers based on the `OPENSHIFT_CLUSTER`
    # environment variable.
    cluster_hosts = [
        server for server in cloud.list_servers()
        if 'metadata' in server and 'clusterid' in server.metadata]

    masters = [server.name for server in cluster_hosts
               if server.metadata['host-type'] == 'master']

    etcd = [server.name for server in cluster_hosts
            if server.metadata['host-type'] == 'etcd']
    if not etcd:
        etcd = masters

    infra_hosts = [server.name for server in cluster_hosts
                   if server.metadata['host-type'] == 'node' and
                   server.metadata['sub-host-type'] == 'infra']

    app = [server.name for server in cluster_hosts
           if server.metadata['host-type'] == 'node' and
           server.metadata['sub-host-type'] == 'app']

    bm_app_hosts = [server for server in cluster_hosts
              if server.metadata['host-type'] == 'node' and
              server.metadata['sub-host-type'] == 'bm_app']
    _update_bm_app_with_kubelet_port(bm_app_hosts, cloud.list_ports())
    bm_app = [bm_app_host.name for bm_app_host in bm_app_hosts]
    app.extend(bm_app)

    nodes = list(set(masters + infra_hosts + app))

    dns = [server.name for server in cluster_hosts
           if server.metadata['host-type'] == 'dns']

    load_balancers = [server.name for server in cluster_hosts
                      if server.metadata['host-type'] == 'lb']

    osev3 = list(set(nodes + etcd + load_balancers))

    inventory['cluster_hosts'] = {'hosts': [s.name for s in cluster_hosts]}
    inventory['OSEv3'] = {'hosts': osev3}
    inventory['masters'] = {'hosts': masters}
    inventory['etcd'] = {'hosts': etcd}
    inventory['nodes'] = {'hosts': nodes}
    inventory['infra_hosts'] = {'hosts': infra_hosts}
    inventory['app'] = {'hosts': app}
    inventory['bm_app'] = {'hosts': bm_app}
    inventory['dns'] = {'hosts': dns}
    inventory['lb'] = {'hosts': load_balancers}

    for server in cluster_hosts:
        if 'group' in server.metadata:
            group = server.metadata.group
            if group not in inventory:
                inventory[group] = {'hosts': []}
            inventory[group]['hosts'].append(server.name)

    inventory['_meta'] = {'hostvars': {}}

    for server in cluster_hosts:
        ssh_ip_address = server.public_v4 or server.private_v4
        hostvars = {
            'ansible_host': ssh_ip_address
        }

        public_v4 = server.public_v4 or server.private_v4
        if public_v4:
            hostvars['public_v4'] = server.public_v4
            hostvars['openshift_public_ip'] = server.public_v4
        # TODO(shadower): what about multiple networks?
        if server.private_v4:
            hostvars['private_v4'] = server.private_v4
            # NOTE(shadower): Yes, we set both hostname and IP to the private
            # IP address for each node. OpenStack doesn't resolve nodes by
            # name at all, so using a hostname here would require an internal
            # DNS which would complicate the setup and potentially introduce
            # performance issues.
            hostvars['openshift_ip'] = server.private_v4
            hostvars['openshift_hostname'] = server.private_v4
        if hasattr(server,'kubelet_port_name'):
            hostvars['kubelet_port_name'] = server.kubelet_port_name
        hostvars['openshift_public_hostname'] = server.name

        node_labels = server.metadata.get('node_labels')
        if node_labels:
            hostvars['openshift_node_labels'] = node_labels

        inventory['_meta']['hostvars'][server.name] = hostvars

    kuryr_vars = _get_kuryr_vars(cloud)
    if kuryr_vars:
        inventory['OSEv3']['vars'] = kuryr_vars

    return inventory


def _get_kuryr_vars(cloud_client):
    """Returns a dictionary of Kuryr variables resulting of heat stacking"""
    # TODO: Filter the cluster stack with tags once it is supported in shade
    hardcoded_cluster_name = 'openshift.example.com'
    stack = cloud_client.get_stack(hardcoded_cluster_name)
    if stack is None or stack['stack_status'] != 'CREATE_COMPLETE':
        return None

    data = {}
    for output in stack['outputs']:
        data[output['output_key']] = output['output_value']

    settings = {}
    # TODO: verify this shade block and complete missing vars
    settings['kuryr_openstack_pod_subnet_id'] = data['pod_subnet']
    settings['kuryr_openstack_worker_nodes_subnet_id'] = data['vm_subnet']
    settings['kuryr_openstack_service_subnet_id'] = data['service_subnet']
    settings['kuryr_openstack_pod_sg_id'] = data['pod_access_sg_id']
    settings['kuryr_openstack_pod_project_id'] = (
        cloud_client.current_project_id)

    settings['kuryr_openstack_auth_url'] = cloud_client.auth['auth_url']
    settings['kuryr_openstack_username'] = cloud_client.auth['username']
    settings['kuryr_openstack_password'] = cloud_client.auth['password']
    settings['kuryr_openstack_user_domain_name'] = (
        cloud_client.auth['user_domain_name'])
    settings['kuryr_openstack_project_id'] = cloud_client.current_project_id
    settings['kuryr_openstack_project_domain_name'] = (
        cloud_client.auth['project_domain_name'])
    return settings

def _update_bm_app_with_kubelet_port(hosts, ports):
    names = set([host['name'] for host in hosts])
    bm_ports = defaultdict(list)
    for port in ports:
        port_host = port['binding:host_id']
        if port_host in names:
            bm_ports[port_host].append(port)

    for host in hosts:
        host_bound_ports = bm_ports[host['name']]
        kubelet_port, = [port for port in host_bound_ports if 'kubelet' in port['name']]
        host['private_v4'] = kubelet_port['fixed_ips'][0]['ip_address']
        host['kubelet_port_name'] = kubelet_port['name']


if __name__ == '__main__':
    print(json.dumps(build_inventory(), indent=4, sort_keys=True))

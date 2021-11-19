import pulumi
import pulumi_aws as aws
import pulumi_tls as tls
import json

admin_policy = aws.iam.get_policy(name="AdministratorAccess")
pulumi.export("iam ssm policy", admin_policy.arn)

# create role (cloud watch agent and ssm)
admin_role = aws.iam.Role(
    "ad_profile",
    name="ad_profile",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Sid": "",
                    "Principal": {
                        "Service": "ec2.amazonaws.com",
                    },
                }
            ],
        }
    ),
    managed_policy_arns=[
        admin_policy.arn,
    ],
    tags={
        "Owner": "andy.chuang",
    },
    )

instance_profile = aws.iam.InstanceProfile(
    "instance-profile", role=admin_role.name
)

size = 't2.micro'

ami = aws.ec2.get_ami(most_recent=True,
                  owners=["amazon"],
                  filters=[aws.GetAmiFilterArgs(name="name", values=["amzn-ami-hvm-*"])])

group = aws.ec2.SecurityGroup('web-secgrp',
    description='Enable HTTP access',
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        protocol='tcp',
        from_port=1,
        to_port=65535,
        cidr_blocks=['0.0.0.0/0'],
    )],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0,
        to_port=0,
        protocol="-1",
        cidr_blocks=["0.0.0.0/0"],
        ipv6_cidr_blocks=["::/0"],
    )])

# create key
private_key = tls.PrivateKey('private_key',
              algorithm = 'RSA',
              rsa_bits=2048)
               
pulumi.export('public openssh', private_key.public_key_openssh)
pulumi.export('public pem', private_key.public_key_pem)
pulumi.export('private pem', private_key.private_key_pem)

# create key pair
keypair = aws.ec2.KeyPair("keypair",
    key_name="keypair",
    public_key=private_key.public_key_openssh)

user_data = """
#!/bin/bash
# Installing kubeadm, kubelet and kubectl
cat <<EOF | sudo tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://packages.cloud.google.com/yum/repos/kubernetes-el7-\$basearch
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://packages.cloud.google.com/yum/doc/yum-key.gpg https://packages.cloud.google.com/yum/doc/rpm-package-key.gpg
exclude=kubelet kubeadm kubectl
EOF

# Set SELinux in permissive mode (effectively disabling it)
sudo setenforce 0
sudo sed -i 's/^SELINUX=enforcing$/SELINUX=permissive/' /etc/selinux/config

sudo yum install -y kubelet kubeadm kubectl --disableexcludes=kubernetes

sudo systemctl enable --now kubelet


# Installing eksctl
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# run cluster
eksctl create cluster --name test-cluster-gogogo --region us-east-1 --version 1.17 --nodegroup-name linux-nodes --node-type t3.micro --nodes 3

"""

server = aws.ec2.Instance('web-server-www',
    instance_type=size,
    vpc_security_group_ids=[group.id],
    user_data=user_data,
    iam_instance_profile=instance_profile.name,
    ami=ami.id,
    key_name=keypair.id,
    tags={
        "Name": "eks-runner"
    })

pulumi.export('public_ip', server.public_ip)
pulumi.export('public_dns', server.public_dns)
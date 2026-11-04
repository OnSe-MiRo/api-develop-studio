"""Explicit local-operator OIDC identity provisioning; no automatic signup."""
import argparse
import os
from pathlib import Path
from api_test.identity_store import IdentityStore
from api_test.oidc_client import origin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--issuer',required=True)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--user-id',required=True)
    parser.add_argument('--display-name',required=True)
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--workspace-name',required=True)
    parser.add_argument('--role',choices=['owner','admin','editor','runner','viewer'],required=True)
    args=parser.parse_args()
    origin(args.issuer)
    store=IdentityStore(Path(os.environ.get('STUDIO_DB_PATH',Path(__file__).resolve().parents[1]/'data'/'studio.db')))
    store.provision(issuer=args.issuer,subject=args.subject,user_id=args.user_id,display_name=args.display_name,workspace_id=args.workspace,workspace_name=args.workspace_name,role=args.role)
    print('Identity linked; existing identity ownership was not reassigned.')


if __name__=='__main__':main()

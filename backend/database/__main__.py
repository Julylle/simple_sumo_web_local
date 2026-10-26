"""Initialize/inspect the database without starting a collector or simulation."""
import argparse
import json
from pathlib import Path
from database.catalog import load_mapping, model_catalog
from database.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init', 'catalog', 'local-time'])
    parser.add_argument('--create-database', action='store_true', help='Requires CREATE DATABASE privilege; normally Docker creates it.')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--database', help='Database to initialize or update; defaults to MYSQL_DATABASE.')
    parser.add_argument('--timezone', help='Display timezone, e.g. +08:00 (Shanghai) or a MySQL-supported IANA zone.')
    args = parser.parse_args()
    digest, content, rows = load_mapping()
    if args.command == 'catalog':
        result = {'mapping_rows': len(rows), 'unique_opc_tags': len({r['OpcTag'] for r in rows}), 'mapping_sha': digest}
        if args.project:
            sha, variables = model_catalog(args.project)
            result.update(model_sha=sha, state_variables=len(variables))
        print(json.dumps(result, indent=2))
        return
    store = Store().connect(create=args.create_database, database=args.database)
    try:
        if args.command == 'local-time':
            from database.local_time import install_local_views
            zone = install_local_views(store.connection, args.timezone)
            print(f'Updated raw data and sumo simulation views to {zone}; UTC source tables unchanged.')
            return
        store.initialize(display_timezone=args.timezone)
        store.register_mapping(digest, content, rows)
        print(f'Initialized raw data and sumo simulation; imported all {len(rows)} CSV mappings.')
    finally:
        store.close()


if __name__ == '__main__':
    main()

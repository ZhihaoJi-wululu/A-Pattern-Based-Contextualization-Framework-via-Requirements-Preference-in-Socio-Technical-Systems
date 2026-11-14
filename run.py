"""Start the local PATPREF research workbench."""
import argparse
from apate.server import serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PATPREF goal model contextualization workbench (loopback only)')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('--port must be 1024..65535')
    serve(args.port)

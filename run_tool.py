import sys

if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--self-check':
        from beast_pick.selfcheck import run
        raise SystemExit(run(sys.argv[2], check_game='--check-game' in sys.argv))
    else:
        from beast_pick.app import main
        raise SystemExit(main())

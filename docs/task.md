Traceback (most recent call last):
  File "/app/main.py", line 40, in <module>
    asyncio.run(main())
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/asyncio/base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/app/main.py", line 31, in main
    return await run_foreground()
           ^^^^^^^^^^^^^^^^^^^^^^
  File "/app/foreground.py", line 193, in run_foreground
    config["login"], config["password"]
    ~~~~~~^^^^^^^^^
KeyError: 'login'
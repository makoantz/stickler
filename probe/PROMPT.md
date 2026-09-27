# Task 0 probe: prompts for Bob

Use Bob's default **Code** mode (not Stickler) in the probe run folder created by
`scripts/new_run.sh probe-1 probe`. Paste **Prompt 1**. When Bob has finished,
paste **Prompt 2** in the same task. Do not help Bob or explain the markers.
After Prompt 2, end the task and run `python3 probe/analyze.py <run folder>` from
the stickler repository.

## Prompt 1

This is a test of tooling. Do each step in order, using whatever tool you would
normally use for it. After each step, write one line saying what happened. If a
step fails or is refused, do not retry it and do not work around it; say so,
quote any error or reason text you received word for word, and continue with the
next step.

1. Read `fixture/notes.txt`.
2. Create `fixture/new_file.txt` containing the single line `hello`.
3. In `fixture/notes.txt`, change the line `line two` to `line 2 edited`.
4. Rename `fixture/rename_me.txt` to `fixture/renamed.txt`.
5. Delete `fixture/delete_me.txt`.
6. Run the command `python3 -c "print('probe-ok')"`.
7. Search the files in `fixture/` for the text `needle`.
8. List the files in `fixture/`.
9. Create `fixture/probe_block_file.txt` containing `x`.
10. Run the command `echo hi > fixture/probe_block_cmd.txt`.
11. Create `fixture/probe_exit1_file.txt` containing `x`.
12. Create `fixture/probe_sleep_file.txt` containing `x`.
13. Does any line in your context start with `STICKLER-PROBE-MARKER`? If so, quote it exactly; if not, say "no marker".

Then stop.

## Prompt 2

Two questions, answer each in one line:
(a) Quote exactly any line in your context that starts with `STICKLER-PROBE-MARKER`, or say "no marker".
(b) For steps 9 and 10 above, quote exactly any reason text you received, or say "no reason received".

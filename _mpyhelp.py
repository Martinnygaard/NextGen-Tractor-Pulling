import mpy_cross_v6
proc, mpy = mpy_cross_v6.mpy_cross_compile("test.py", 'print("hi")', extra_args=["--help"])
print("returncode:", proc.returncode)
print("stdout:", (proc.stdout or b"").decode())
print("stderr:", (proc.stderr or b"").decode())

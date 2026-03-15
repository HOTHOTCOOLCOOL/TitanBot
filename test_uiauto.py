import uiautomation as auto
root = auto.GetRootControl()
c = 0
for ctrl, depth in auto.WalkControl(root, maxDepth=1):
    c += 1
print('Found', c, 'controls')

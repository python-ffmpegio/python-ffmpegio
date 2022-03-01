from ffmpegio import actions, plugins
import demo_actions1, demo_actions2

def test_actions():
    plugins.pm.register(demo_actions1)
    plugins.pm.register(demo_actions2)

    assert actions.__dir__()==['doA','doB','doC']

    assert actions.doB()=='B'
    assert actions.doC()=='C'
    assert actions.doA()=='D'

if __name__=='__main__':
    test_actions()
    
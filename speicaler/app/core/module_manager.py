class ModuleManager:
    def __init__(self):
        self._modules = {}

    def register(self, name, module):
        self._modules[name] = module

    def get(self, name):
        return self._modules.get(name)

    def all(self):
        return self._modules

from abc import abstractmethod
import json
import os
import re

from typing_extensions import override

class Output:
    def __init__(self) -> None:
        self.context = dict[str, dict]()
        pass

    @abstractmethod
    def write(self, what: str):
        pass

class Node:
    _uuid = 0

    def __init__(self, name: str, ip: str, type: str, parent: object = None) -> None:
        self.name = name
        self.parent = parent
        self.type = type
        self.ip = ip
        self._id = Node._uuid
        Node._uuid += 1
        if size := Node.mask_size(ip):
            self._mask_size = size
            self._mask = Node.masked(ip, size)
        else:
            self._mask_size = 0
            self._mask = None

    def __repr__(self):
        return f"{{ id: {self._id}, name: {self.name}, type: {self.type}, ip: {self.ip}, mask: {self._mask} }}"

    @abstractmethod
    def connect(self, other) -> None:
        pass 

    @abstractmethod
    def display(self, out: Output) -> None:
        pass 

    def debug(self) -> None:
        print(self)

    @staticmethod
    def maskof(ip: str) -> str|None:
        if size := Node.mask_size(ip):
            return Node.masked(ip, size)
        return None

    @staticmethod
    def mask_size(ip: str) -> int|None:
        if ip.find('/') == -1:
            return None
        return int(ip.split('/')[-1])

    @staticmethod
    def masked(ip: str, size: int) -> str|None:
        ipm = ip.split('.')
        ipx = list[str]()
        for i in ipm:
            if i.find('/') != -1:
                i = i.split('/')[0]
            ipx.append(f"{int(i):b}".rjust(8, "0"))
        return ".".join([str(int(x, 2) if x != "" else "0") for x in re.sub("([0-9]{0,8})", "\\1.", "".join(ipx)[0:size])[0:-1].split(".")])

class Network(Node):
    def __init__(self, name: str, ip: str, type: str, parent: object = None) -> None:
        super().__init__(name, ip, type, parent)
        self.subnodes = dict[str, Node]()
        self._mesh_only = False

    def add(self, node: Node):
        self.subnodes[node.ip] = node

    @override
    def display(self, out: Output) -> None:
        super().display(out)
        if not self._mesh_only:
            out.write(f"subgraph __n{self._id} [\"`Rede {self.ip}`\"]")
            out.write(f"__{self._id}{{\"`{self.name}`\"}}")
        else:
            out.write(f"subgraph __n{self._id} [\"`{self.name}`\"]")
        for node in self.subnodes.values():
            node.display(out)
            if not self._mesh_only:
                out.write(f"__{self._id} {self.name + node.name}@---- __{node._id}")
        out.write("end")


class Router(Network):
    def __init__(self, name: str, ip: str) -> None:
        super().__init__(name, ip, "ROUTER")
        self.neighbors = list[Network]()

    @override
    def connect(self, other: Network) -> None:
        if other in self.neighbors:
            return
        self.neighbors.append(other)
        other.connect(self)

    @override
    def display(self, out: Output) -> None:
        super().display(out)
        if "visits" not in out.context:
            out.context["visits"] = {}
        for neighbor in self.neighbors:
            Router.show_mesh(self, neighbor, out, out.context["visits"])

    @staticmethod
    def show_mesh(a: Node, b: Node, out: Output, visited: dict[int, list[int]]) -> None:
        if (a._id in visited) and (b._id in visited[a._id]):
            return
        if (b._id in visited) and (a._id in visited[b._id]):
            return
        if a._id not in visited:
            visited[a._id] = []
        if b._id not in visited:
            visited[b._id] = []
        visited[a._id].append(b._id)
        visited[b._id].append(a._id)
        out.write(f"__{a._id} {a.name + b.name}@---- __{b._id}")

class Computer(Node):
    def __init__(self, name: str, ip: str, parent: object) -> None:
        super().__init__(name, ip, "HOST", parent)

    @override
    def connect(self, other: Network) -> None:
        if self.parent:
            return
        self.parent = other
        other.add(self)

    @override
    def display(self, out: Output) -> None:
        super().display(out)
        return out.write(f"__{self._id}{{\"`{self.name} :: {self.ip}`\"}}")

class Structure(Network):
    def __init__(self, name: str) -> None:
        super().__init__(name, "", "VIEW", None)
        self._mesh_only = True

class NetMap:
    def __init__(self, path: str) -> None:
        self.structure = Structure("Estrutura")
        data = []
        with open(path, "r") as f:
            data = json.load(f)
        hosts = []
        routers = []
        mesh    = dict[Node,list[str]]()
        rmesh   = dict[str,Node]()
        net     = dict[str,Router]()
        for device in data:
            if device["type"] == "HOST":
                hosts.append(device)
            elif device["type"] == "ROUTER":
                routers.append(device)
        for router in routers:
            node = Router(router["name"], router["mask"])
            rmesh[router["mask"]] = node
            for port in router["ports"]:
                if port["type"] == "R2R":
                    if "topnet" not in port:
                        raise KeyError()
                    if node not in mesh:
                        mesh[node] = [port["topnet"]]
                    else:
                        mesh[node].append(port["topnet"])
                elif port["type"] == "NETWORK":
                    net[Node.maskof(node.ip) or node.ip] = node
            self.structure.add(node)
        for m in mesh:
            for t in mesh[m]:
                rmesh[t].connect(m)
        for host in hosts:
            parent : Network|None = None
            for router in net.values():
                if Node.masked(host["ip"], router._mask_size) == router._mask:
                    parent = router
            if parent is not None:
                node = Computer(host["name"], host["ip"], parent)
                Network.add(parent, node)

class IOWriter(Output):
    @override
    def write(self, what: str):
        print(what)
        pass 

class Mapper:
    @staticmethod
    def map_path(io: Output, file: str, path: list[str]):
        NetMap(os.getcwd() + file).structure.display(io)
        for i in range(len(path)-1):
            io.write(f"linkStyle {path[i]}{path[i+1]} stroke:red;")

if __name__ == "__main__":
    io = IOWriter()
    io.write("```mermaid")
    io.write("graph LR")
    Mapper.map_path(IOWriter(), "/../topologia.json", ["H1", "R1", "R2", "R3", "H4"])

    io.write("```")

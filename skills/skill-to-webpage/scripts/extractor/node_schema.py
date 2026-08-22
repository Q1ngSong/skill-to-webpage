from dataclasses import dataclass, field


@dataclass
class ResourceRef:
    path: str
    exists: bool


@dataclass
class Node:
    id: str
    title: str
    content: str
    line_start: int
    line_end: int
    resources: list[ResourceRef] = field(default_factory=list)


@dataclass
class SkillBackbone:
    skill_name: str
    description: str
    source_path: str
    nodes: list[Node] = field(default_factory=list)

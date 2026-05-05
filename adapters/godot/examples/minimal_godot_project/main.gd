extends Node3D

## Minimal AgentBridge example -- spawns a player Node3D in the
## "player" group + an AgentBridge node.

func _ready() -> void:
    var player := Node3D.new()
    player.name = "Player"
    player.add_to_group("player")
    add_child(player)
    var head := Node3D.new()
    head.name = "Head"
    player.add_child(head)
    var bridge_script: GDScript = load("res://addons/agentbridge/agent_bridge.gd")
    var bridge := Node.new()
    bridge.name = "AgentBridge"
    bridge.set_script(bridge_script)
    add_child(bridge)

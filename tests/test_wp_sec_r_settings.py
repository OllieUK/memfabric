import json
import pathlib
import pytest

SETTINGS_PATH = pathlib.Path(__file__).parent.parent / ".claude" / "settings.json"


@pytest.fixture(scope="module")
def settings():
    with open(SETTINGS_PATH) as f:
        return json.load(f)


def test_settings_json_is_valid_json():
    data = json.load(SETTINGS_PATH.open())
    assert isinstance(data, dict)


def test_r10_destructive_git_entries_present(settings):
    ask = settings["permissions"]["ask"]
    r10_entries = [
        "Bash(git push --force*)",
        "Bash(git push --force-with-lease*)",
        "Bash(git push -f*)",
        "Bash(git reset --hard*)",
        "Bash(git clean -f*)",
        "Bash(git branch -D *)",
        "Bash(git branch -d *)",
        "Bash(git checkout .*)",
        "Bash(git checkout -- *)",
        "Bash(git restore .*)",
        "Bash(git restore --source*)",
    ]
    for entry in r10_entries:
        assert entry in ask, f"Missing R10 entry: {entry}"


def test_r12_supply_chain_entries_present(settings):
    ask = settings["permissions"]["ask"]
    r12_entries = [
        "Bash(wget*)",
        "Bash(uv pip install*)",
        "Bash(uv add*)",
        "Bash(npm install*)",
        "Bash(npm i *)",
        "Bash(yarn add*)",
        "Bash(pnpm add*)",
        "Bash(cargo install*)",
        "Bash(go install*)",
        "Bash(gem install*)",
        "Bash(brew install*)",
    ]
    for entry in r12_entries:
        assert entry in ask, f"Missing R12 entry: {entry}"


def test_existing_ask_entries_unchanged(settings):
    ask = settings["permissions"]["ask"]
    original_33 = [
        "Edit(/home/oliver/projects/graph-memory-fabric/hooks/_filters.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/hooks/_filters.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/hooks/session_start.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/hooks/session_start.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/hooks/post_tool_use.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/hooks/post_tool_use.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/.claude/settings.json)",
        "Edit(/home/oliver/projects/graph-memory-fabric/.claude/settings.local.json)",
        "Edit(/home/oliver/projects/graph-memory-fabric/.mcp.json)",
        "Edit(/home/oliver/projects/graph-memory-fabric/docker-compose.yml)",
        "Edit(/home/oliver/projects/graph-memory-fabric/CLAUDE.md)",
        "Edit(/home/oliver/projects/graph-memory-fabric/scripts/seed_strands.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/scripts/dump_db.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/scripts/restore_db.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/scripts/init_schema.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/scripts/init_knowledge_schema.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/scripts/seed_strands.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/scripts/dump_db.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/scripts/restore_db.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/scripts/init_schema.py)",
        "Write(/home/oliver/projects/graph-memory-fabric/scripts/init_knowledge_schema.py)",
        "Edit(/home/oliver/projects/graph-memory-fabric/BACKLOG.md)",
        "Write(/home/oliver/projects/graph-memory-fabric/BACKLOG.md)",
        "Edit(/home/oliver/projects/graph-memory-fabric/data/frameworks/**)",
        "Write(/home/oliver/projects/graph-memory-fabric/data/frameworks/**)",
        "Edit(/home/oliver/projects/graph-memory-fabric/data/threats/**)",
        "Write(/home/oliver/projects/graph-memory-fabric/data/threats/**)",
        "Bash(sudo*)",
        "Bash(pip install *)",
        "Bash(curl http*)",
        "Bash(curl https*)",
        "Bash(docker compose down*)",
        "Bash(docker volume *)",
    ]
    for entry in original_33:
        assert entry in ask, f"Pre-existing ask entry removed or modified: {entry}"


def test_existing_deny_entries_unchanged(settings):
    deny = settings["permissions"]["deny"]
    expected_deny = [
        "Write(/home/oliver/projects/graph-memory-fabric/.env)",
        "Edit(/home/oliver/projects/graph-memory-fabric/.env)",
        "Write(/home/oliver/projects/graph-memory-fabric/.env.*)",
        "Edit(/home/oliver/projects/graph-memory-fabric/.env.*)",
        "Bash(docker compose down -v*)",
        "Bash(docker-compose down -v*)",
        "Bash(docker volume rm *memgraph*)",
        "Bash(rm -rf /home/oliver/projects/graph-memory-fabric/data/*)",
        "Bash(python3 /home/oliver/projects/graph-memory-fabric/scripts/seed_strands.py*)",
        "Bash(python /home/oliver/projects/graph-memory-fabric/scripts/seed_strands.py*)",
        "Read(/home/oliver/projects/graph-memory-fabric/data/ingest-quarantine/**)",
    ]
    for entry in expected_deny:
        assert entry in deny, f"Deny entry missing or modified: {entry}"
    assert len(deny) == 11


def test_existing_allow_entries_unchanged(settings):
    allow = settings["permissions"]["allow"]
    expected_allow = [
        "Read(/home/oliver/**)",
        "Read(/mnt/c/Users/olive/**)",
        "Read(/tmp/**)",
        "Read(/proc/sys/vm/**)",
        "Edit(/home/oliver/projects/**)",
        "Write(/home/oliver/projects/**)",
        "Edit(/home/oliver/.claude/skills/**)",
        "Edit(/home/oliver/.claude/plans/**)",
        "Write(/home/oliver/.claude/plans/**)",
        "Bash(ls*)",
        "Bash(cd*)",
        "Bash(cat*)",
        "Bash(head*)",
        "Bash(tail*)",
        "Bash(pwd)",
        "Bash(echo*)",
        "Bash(printenv*)",
        "Bash(which*)",
        "Bash(mkdir*)",
        "Bash(touch*)",
        "Bash(pkill -f memory-mcp)",
        "Bash(fuser -k 8000/tcp)",
        "Bash(git *)",
        "Bash(python *)",
        "Bash(python3 *)",
        "Bash(pytest*)",
        "Bash(pip install -r*)",
        "Bash(pip3 install -r*)",
        "Bash(pip show*)",
        "Bash(pip list*)",
        "Bash(pip freeze*)",
        "Bash(docker ps*)",
        "Bash(docker logs*)",
        "Bash(docker exec memgraph*)",
        "Bash(docker compose up*)",
        "Bash(docker compose restart*)",
        "Bash(docker compose logs*)",
        "Bash(docker compose ps*)",
        "Bash(docker compose config*)",
        "Bash(curl http://127.0.0.1*)",
        "Bash(curl http://localhost*)",
        "Bash(gh *)",
        "WebSearch",
        "WebFetch(domain:memgraph.com)",
        "WebFetch(domain:python.org)",
        "WebFetch(domain:docs.pydantic.dev)",
        "WebFetch(domain:fastapi.tiangolo.com)",
        "mcp__memory__*",
        "mcp__claude_ai_Notion__notion-fetch",
        "mcp__claude_ai_Notion__notion-search",
    ]
    for entry in expected_allow:
        assert entry in allow, f"Allow entry missing or modified: {entry}"


def test_ask_array_has_no_duplicates(settings):
    ask = settings["permissions"]["ask"]
    assert len(ask) == len(set(ask)), "Duplicate entries found in ask array"


def test_curl_localhost_allow_still_present(settings):
    allow = settings["permissions"]["allow"]
    assert "Bash(curl http://127.0.0.1*)" in allow
    assert "Bash(curl http://localhost*)" in allow

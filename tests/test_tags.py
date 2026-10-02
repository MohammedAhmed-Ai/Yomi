from fastapi import status

def test_list_tags_empty(client):
    """Verify that listing tags returns an empty list when no tags exist."""
    response = client.get("/api/tags/")
    assert response.status_code == 200
    assert response.json() == []

def test_create_tag_success(client):
    """Verify that a tag can be created successfully."""
    payload = {"name": "Work", "color": "#FF0000"}
    response = client.post("/api/tags/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Work"
    assert data["color"] == "#FF0000"
    assert "id" in data

def test_create_tag_default_color(client):
    """Verify that a tag is created with the default color if not provided."""
    payload = {"name": "Personal"}
    response = client.post("/api/tags/", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Personal"
    assert data["color"] == "#888888"

def test_create_tag_duplicate_name(client):
    """Verify that creating a tag with a duplicate name returns a 409 Conflict."""
    payload = {"name": "Shopping", "color": "#00FF00"}
    # First creation
    client.post("/api/tags/", json=payload)
    # Duplicate creation
    response = client.post("/api/tags/", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "Tag with this name already exists"

def test_create_tag_invalid_color(client):
    """Verify that an invalid color hex code returns a 422 Unprocessable Entity."""
    payload = {"name": "Invalid", "color": "red"} # Not a hex code
    response = client.post("/api/tags/", json=payload)
    assert response.status_code == 422

def test_create_tag_empty_name(client):
    """Verify that an empty tag name returns a 422 Unprocessable Entity."""
    payload = {"name": "", "color": "#000000"}
    response = client.post("/api/tags/", json=payload)
    assert response.status_code == 422

def test_list_tags_populated(client):
    """Verify that listing tags returns all created tags."""
    tags = [
        {"name": "Tag1", "color": "#111111"},
        {"name": "Tag2", "color": "#222222"},
    ]
    for tag in tags:
        client.post("/api/tags/", json=tag)
    
    response = client.get("/api/tags/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [t["name"] for t in data]
    assert "Tag1" in names
    assert "Tag2" in names

import base64
import requests

import time
def upload_pdf_to_github(
    owner,
    repo,
    folder,
    file_name,
    token,
    pdf_bytes=None,
    pdf_base64=None,
    file_path=None,
):

    # Convert input PDF to base64
    if pdf_bytes is not None:
        content_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    elif pdf_base64 is not None:
        content_base64 = pdf_base64
    elif file_path is not None:
        with open(file_path, "rb") as f:
            content_base64 = base64.b64encode(f.read()).decode("utf-8")
    else:
        raise ValueError("Provide pdf_bytes, pdf_base64 or file_path")

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{folder}/{file_name}"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

    # 🔍 STEP 1: Check if the file already exists → get SHA for overwrite
    sha = None
    check = requests.get(api_url, headers=headers)

    if check.status_code == 200:
        sha = check.json().get("sha")

    # 📤 STEP 2: Upload (create/update)
    payload = {"message": f"Overwrite {file_name}", "content": content_base64}

    if sha:
        payload["sha"] = sha

    put = requests.put(api_url, json=payload, headers=headers)

    if put.status_code not in (200, 201):
        raise Exception(f"GitHub Error {put.status_code}: {put.text}")

    # ⭐ NEW → Fetch commit sha for CDN cache-bypass
    commit_sha = put.json()["commit"]["sha"]

    # Viewable links
    view_link = f"https://github.com/{owner}/{repo}/blob/main/{folder}/{file_name}?raw=1"

    # ⭐ NEW → 100% UPDATED link using commit hash
    cdn_link = (
        f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{commit_sha}/{folder}/{file_name}"
    )

    return {
        "link": cdn_link,
        
    }

#!/usr/bin/env python3
"""
GitHub Artifact Downloader
Downloads the latest artifacts from a source repository and saves them locally.
"""

import os
import sys
import json
import time
import zipfile
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple


class GitHubArtifactDownloader:
    """Handles downloading artifacts from GitHub repositories."""
    
    def __init__(self, token: str, source_repo: str):
        """
        Initialize the downloader.
        
        Args:
            token: GitHub personal access token
            source_repo: Source repository in format 'owner/repo'
        """
        self.token = token
        self.source_repo = source_repo
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    
    def get_latest_workflow_runs(self, status: str = "completed") -> List[Dict]:
        """
        Get the latest workflow runs for the repository.
        
        Args:
            status: Filter by workflow run status (completed, in_progress, etc.)
        
        Returns:
            List of workflow runs
        """
        url = f"{self.base_url}/repos/{self.source_repo}/actions/runs"
        params = {
            "status": status,
            "per_page": 10,
            "page": 1
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            runs = response.json()
            
            # Sort by creation date descending to get latest runs
            if "workflow_runs" in runs:
                runs["workflow_runs"].sort(
                    key=lambda x: x.get("created_at", ""),
                    reverse=True
                )
                return runs["workflow_runs"]
            
            return []
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching workflow runs: {e}")
            return []
    
    def get_artifacts_for_run(self, run_id: int) -> List[Dict]:
        """
        Get all artifacts for a specific workflow run.
        
        Args:
            run_id: The workflow run ID
        
        Returns:
            List of artifacts
        """
        url = f"{self.base_url}/repos/{self.source_repo}/actions/runs/{run_id}/artifacts"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get("artifacts", [])
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching artifacts for run {run_id}: {e}")
            return []
    
    def download_artifact(self, artifact_id: int, artifact_name: str, download_path: Path) -> bool:
        """
        Download a specific artifact by ID.
        
        Args:
            artifact_id: The artifact ID
            artifact_name: Name of the artifact
            download_path: Path to save the artifact
        
        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/repos/{self.source_repo}/actions/artifacts/{artifact_id}/zip"
        
        try:
            print(f"📥 Downloading artifact: {artifact_name}")
            response = requests.get(url, headers=self.headers, stream=True)
            response.raise_for_status()
            
            # Save the zip file
            zip_path = download_path / f"{artifact_name}.zip"
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print(f"✅ Artifact downloaded: {zip_path}")
            return True
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Error downloading artifact {artifact_name}: {e}")
            return False
    
    def extract_artifact(self, zip_path: Path, extract_path: Path) -> bool:
        """
        Extract a zip artifact to the specified path.
        
        Args:
            zip_path: Path to the zip file
            extract_path: Path to extract the contents
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create a subfolder for each artifact
            artifact_folder = extract_path / zip_path.stem
            artifact_folder.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(artifact_folder)
            
            print(f"📦 Extracted to: {artifact_folder}")
            
            # Remove the zip file after extraction
            zip_path.unlink()
            
            return True
        
        except zipfile.BadZipFile as e:
            print(f"❌ Error extracting {zip_path}: {e}")
            return False
    
    def get_latest_artifacts(self, artifact_filter: Optional[str] = None) -> List[Tuple[Dict, Dict]]:
        """
        Get the latest artifacts across recent workflow runs.
        
        Args:
            artifact_filter: Optional filter for artifact name
        
        Returns:
            List of tuples (run, artifact)
        """
        runs = self.get_latest_workflow_runs()
        if not runs:
            print("⚠️ No completed workflow runs found")
            return []
        
        artifacts_data = []
        seen_artifacts = set()
        
        # Iterate through runs to find unique artifacts
        for run in runs:
            artifacts = self.get_artifacts_for_run(run["id"])
            
            for artifact in artifacts:
                artifact_name = artifact.get("name", "unknown")
                
                # Skip expired artifacts
                if artifact.get("expired", False):
                    continue
                
                # Apply name filter if specified
                if artifact_filter and artifact_filter not in artifact_name:
                    continue
                
                # Only get the latest version of each artifact
                if artifact_name not in seen_artifacts:
                    seen_artifacts.add(artifact_name)
                    artifacts_data.append((run, artifact))
                    print(f"📋 Found artifact: {artifact_name} (Run: {run['name']})")
        
        return artifacts_data
    
    def save_metadata(self, artifacts_data: List[Tuple[Dict, Dict]], target_path: Path):
        """Save metadata about downloaded artifacts."""
        metadata = {
            "source_repository": self.source_repo,
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            "artifacts": [
                {
                    "name": artifact["name"],
                    "size_bytes": artifact.get("size_in_bytes", 0),
                    "created_at": artifact.get("created_at", ""),
                    "workflow_run": {
                        "id": run["id"],
                        "name": run.get("name", ""),
                        "created_at": run.get("created_at", ""),
                        "head_branch": run.get("head_branch", ""),
                        "head_sha": run.get("head_sha", "")
                    }
                }
                for run, artifact in artifacts_data
            ]
        }
        
        metadata_path = target_path / "artifacts_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"📝 Metadata saved to: {metadata_path}")


def main():
    """Main execution function."""
    print("🚀 GitHub Artifact Downloader")
    print("=" * 50)
    
    # Get environment variables
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("❌ GITHUB_TOKEN environment variable is not set")
        sys.exit(1)
    
    source_repo = os.environ.get("SOURCE_REPO", "owner/repository-name")
    artifact_filter = os.environ.get("ARTIFACT_NAME", "")
    target_folder = os.environ.get("TARGET_FOLDER", "downloaded-artifacts")
    
    # Create target directory
    target_path = Path(target_folder)
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize downloader
    downloader = GitHubArtifactDownloader(github_token, source_repo)
    
    # Get latest artifacts
    print(f"\n🔍 Searching for artifacts in: {source_repo}")
    if artifact_filter:
        print(f"🎯 Filtering for artifact name containing: {artifact_filter}")
    
    artifacts_data = downloader.get_latest_artifacts(artifact_filter if artifact_filter else None)
    
    if not artifacts_data:
        print("⚠️ No artifacts found matching the criteria")
        return
    
    print(f"\n📦 Found {len(artifacts_data)} artifact(s) to download")
    print("-" * 50)
    
    # Download and extract each artifact
    successful_downloads = []
    for run, artifact in artifacts_data:
        artifact_name = artifact["name"]
        artifact_id = artifact["id"]
        
        print(f"\n⏳ Processing: {artifact_name}")
        
        # Download
        if downloader.download_artifact(artifact_id, artifact_name, target_path):
            # Extract
            zip_path = target_path / f"{artifact_name}.zip"
            if downloader.extract_artifact(zip_path, target_path):
                successful_downloads.append((run, artifact))
        
        time.sleep(1)  # Rate limiting
    
    # Save metadata
    if successful_downloads:
        downloader.save_metadata(successful_downloads, target_path)
    
    print("\n" + "=" * 50)
    print(f"✅ Successfully processed {len(successful_downloads)}/{len(artifacts_data)} artifacts")
    print(f"📁 Files saved to: {target_path.absolute()}")
    print("🎉 Done!")


if __name__ == "__main__":
    main()

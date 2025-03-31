import os
import uuid
from git import Repo as GitRepo, GitCommandError
from pathlib import Path


class Repo:
    def __init__(self, repo_name_or_url: str, is_url: bool = False):
        """
        Initialize the Repo class.
        If `is_url` is False, create a new local repository with the given name.
        If `is_url` is True, clone the repository from the given URL.
        """
        self.local_path = Path(f"./{uuid.uuid4()}")  # Create a unique local folder
        if is_url:
            # Clone the repository from the URL
            self.repo = GitRepo.clone_from(repo_name_or_url, self.local_path)
        else:
            # Create a new repository locally
            self.local_path.mkdir(parents=True, exist_ok=True)
            self.repo = GitRepo.init(self.local_path)
            (self.local_path / ".gitignore").write_text("# Add files to ignore\n")
            self.repo.index.add([".gitignore"])
            self.repo.index.commit("Initial commit")

    def load_files(self) -> dict:
        """
        Load all files in the repository into a dictionary.
        Only files visible to Git (not ignored by .gitignore) are included.
        The keys are file paths, and the values are the file contents as strings.
        """
        files_dict = {}
        try:
            # Use Git's ls-files to get a list of tracked files
            tracked_files = self.repo.git.ls_files().splitlines()
            for file_path in tracked_files:
                full_path = self.local_path / file_path
                if full_path.is_file():
                    files_dict[file_path] = full_path.read_text(encoding="utf-8")
        except GitCommandError as e:
            raise RuntimeError(f"Error loading files: {e}")
        return files_dict

    def update_files(self, files_dict: dict):
        """
        Update files in the repository based on the given dictionary.
        The keys are file paths, and the values are the new file contents.
        """
        for file_path, content in files_dict.items():
            full_path = self.local_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure parent directories exist
            full_path.write_text(content, encoding="utf-8")
            self.repo.index.add([str(full_path.relative_to(self.local_path))])
        self.repo.index.commit("Updated files")

    def create_branch(self, branch_name: str):
        """Create a new branch."""
        self.repo.git.branch(branch_name)

    def checkout_branch(self, branch_name: str):
        """Checkout an existing branch."""
        self.repo.git.checkout(branch_name)

    def add_and_commit(self, message: str):
        """Add all changes and commit with the given message."""
        self.repo.git.add(A=True)
        self.repo.index.commit(message)

    def set_upstream(self, branch_name: str, remote_name: str = "origin"):
        """Set upstream for the current branch."""
        self.repo.git.push("--set-upstream", remote_name, branch_name)

    def create_pr(self, title: str, body: str, base: str = "main", head: str = None):
        """
        Create a pull request.
        This requires the GitHub CLI (`gh`) to be installed and authenticated.
        """
        head = head or self.repo.active_branch.name
        os.system(f'gh pr create --title "{title}" --body "{body}" --base "{base}" --head "{head}"')


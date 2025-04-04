import os
import uuid
import shutil
from pathlib import Path
from git import Repo as GitRepo, GitCommandError
from app.config import logger


class Repo:
    name: str
    uuid: str
    local_path: Path
    def __init__(self, name: str = "", url: str = ""):
        """
        Initialize the Repo object.
        If a URL is provided, clone the repository from that URL.
        If a name is provided, create a new local repository with that name.
        """
        if name is None and url is None:
            raise ValueError("Either name or URL must be provided.")

        self.uuid = str(uuid.uuid4())

        if name is not None:
            logger.info("Creating a new repository with name: %s", name)
            self.name = name
            self.local_path = Path(f"./repos/{self.uuid}/{name}")  # Create a unique local folder

            # Create a new repository locally
            self.local_path.mkdir(parents=True, exist_ok=True)
            self.repo = GitRepo.init(self.local_path)
            (self.local_path / ".gitignore").write_text("# Add files to ignore\n")
            self.repo.index.add([".gitignore"])
            self.repo.index.commit("Initial commit")
        else:
            logger.info("Cloning repository from URL: %s", url)
            # Clone the repository from the URL
            self.local_path = Path(f"./repos/{self.uuid}/")  # Create a unique local folder

            # Create a new repository locally
            self.local_path.mkdir(parents=True, exist_ok=True)

            self.repo = GitRepo.clone_from(url, self.local_path)


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
            raise RuntimeError("Error loading files: %s" % e)
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
            #self.repo.index.add([str(full_path.relative_to(self.local_path))])
        #self.repo.index.commit("Updated files")

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

    def get_diff(self, staged: bool = False) -> str:
        """
        Get the git diff of the repository.
        
        Args:
            staged (bool): If True, show the diff of staged changes. 
                           If False, show the diff of unstaged changes.
        
        Returns:
            str: The git diff output as a string.
        """
        try:
            if staged:
                # Get the diff of staged changes
                diff = self.repo.git.diff("--cached")
            else:
                # Get the diff of unstaged changes
                diff = self.repo.git.diff()
            return diff
        except GitCommandError as e:
            raise RuntimeError(f"Error getting git diff: {e}") from e

    def create_zip(self, output_path: str = None) -> str:
        """
        Create a ZIP file of the repository.

        Args:
            output_path (str): The path where the ZIP file will be saved. 
                               If None, it will be saved in the same directory as the repo.

        Returns:
            str: The path to the created ZIP file.
        """
        if output_path is None:
            output_path = str(self.local_path) + ".zip"

        try:
            shutil.make_archive(str(self.local_path), 'zip', str(self.local_path))
            return output_path
        except Exception as e:
            raise RuntimeError(f"Error creating ZIP file: {e}") from e

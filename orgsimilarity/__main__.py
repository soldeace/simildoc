import argparse
import os
import re
import sys
from pathlib import Path
import numpy as np
import functools
import orgparse

from nltk.stem import SnowballStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

STOPWORDS_FILENAME = "stopwords.txt"
JUNKCHARS_FILENAME = "junkchars.txt"
FILES_EXT = "*.org"
SCRIPT_PATH = Path(__file__).parent

# Fetches filenames in the same directory of the script
def get_stopwords() -> list:
    """Get a list of stopwords from STOPWORDS file."""
    with open(SCRIPT_PATH / STOPWORDS_FILENAME, "r") as f:
        stopwords = f.read().split("\n")
    return stopwords

def get_junkchars() -> list:
    """Get a list of junk characters from JUNKCHARS file."""
    with open(SCRIPT_PATH / JUNKCHARS_FILENAME, "r") as f:
        junkchars = f.read().split("\n")
        # remove empty element, which will probably exist in the file
        junkchars = [char for char in junkchars if char]
    return junkchars


def parse_args():
    """Parse command line arguments."""
    p = argparse.ArgumentParser()
    p.add_argument(
        "--input_filename",
        "-i",
        type=str,
        help="input filename",
        required=True,
    )
    p.add_argument(
        "--directory",
        "-d",
        type=str,
        help="directory of files to search",
        required=True,
    )
    p.add_argument(
        "--number",
        "-n",
        type=int,
        default=10,
        help="number of similar documents (default: 10)",
        required=False,
    )
    p.add_argument(
        "--language",
        "-l",
        type=str,
        default="english",
        help="nltk's SnowballStemmer language (default: english)",
        required=False,
    )
    p.add_argument(
        "--scores",
        "-s",
        action="store_true",
        help="show cosine similarity scores (default: False)",
        required=False,
    )
    p.add_argument(
        "--recursive",
        "-r",
        help="search for org files recursively (default: False)",
        action="store_true",
        required=False,
    ),
    p.add_argument(
        "--id-links",
        "-I",
        action="store_true",
        help="create ID links instead of FILE links (default: False)",
        required=False,
    )
    return p.parse_args()


def read_file(filename: Path) -> str:
    """Safely reads a filename and returns its content."""
    with open(filename, "r") as open_file:
        return open_file.read()


def get_tokens(text, stemmer, junkchars: list, stopwords: list) -> list:
    """
    Preprocess a text and returns a list of tokens.
    """
    text = text.lower()
    # Replaces the stupid apostrophe with a normal one.
    # This step is needed because there's an Emacs package for posh people
    # that transforms every punctuation into fancy unicode symbols, and
    # this screws with the stopwords filter some lines below.
    text = text.replace("’", "'")
    # Remove org-mode front matter and other special characters
    # that could leak into the tokens list.
    for junkchar in junkchars:
        text = text.replace(junkchar, "")
    # Replace carriage returns with a space.
    text = text.replace("\n", " ")
    tokens = text.split(" ")
    # Strip stopwords.
    tokens = [w for w in tokens if w not in stopwords]
    # Replace tokens with their stems.
    # I tried using a lemmatizer like nltk's WordNet and spacy, but they
    # didn't cause much difference in the final results that could justify
    # a threefold increase in processing time.
    tokens = [stemmer(w) for w in tokens]
    return tokens


def get_scores(input_filename, target_filenames, stemmer):
    """Create a document similarity table based on TF-IDF and cosine dist.

    This function scans the a directory for org files and creates a sparse
    matrix with all found tokens via tf-idf algorithm (short for term
    frequency-inverse document frequency), which penalizes words that appear too
    often in a text."""
    stopwords = get_stopwords()
    junkchars = get_junkchars()
    base_document = orgparse.load(input_filename).get_body(format="plain")
    documents = [
        orgparse.load(f).get_body(format="plain") for f in target_filenames
    ]
    tokenizer = functools.partial(get_tokens, stemmer=stemmer, junkchars=junkchars, stopwords=stopwords)
    vectorizer = TfidfVectorizer(tokenizer=tokenizer, token_pattern=None)

    # To make uniformed vectors, both documents need to be combined first.
    documents.insert(0, base_document)
    embeddings = vectorizer.fit_transform(documents)
    scores = cosine_similarity(embeddings[0], embeddings[1:]).flatten()

    return scores


def format_results(
    input_path: Path,
    targets: Path,
    scores: np.ndarray,
    num_results: int,
    id_links: bool,
    show_scores: bool,
) -> list:
    """Format results in an org-compatible format with links."""
    results = zip(scores, targets)
    sorted_results = sorted(results, key=lambda x: x[0], reverse=True)
    valid_results = sorted_results[:num_results]
    formatted_results = []
    for score, target in valid_results:
        org_content = orgparse.load(target)
        title = org_content.get_file_property("title")
        score_output = f"{score:.3f} " if show_scores else ""
        if id_links:
            target_id = org_content.get_property("ID")
            link_ref = f"id:{target_id}"
        else:
            # org-mode links use relative rather than absolute paths
            target_rel_path = target.relative_to(input_path.parent)
            link_ref = f"file:{target_rel_path}"
        entry = f"{score_output}[[{link_ref}][{title}]]"
        formatted_results.append(entry)
    return formatted_results


def main():
    """Execute main function."""
    args = parse_args()
    input_path = Path(args.input_filename)
    directory = Path(args.directory)
    num_results = args.number
    language = args.language
    show_scores = args.scores
    recursive = args.recursive
    id_links = args.id_links

    stemmer = SnowballStemmer(language).stem
    target_glob = (
        directory.rglob(FILES_EXT) if recursive else directory.glob(FILES_EXT)
    )
    target_filenames = [f for f in target_glob]

    scores = get_scores(
        input_filename=input_path,
        target_filenames=target_filenames,
        stemmer=stemmer,
    )
    results = format_results(
        input_path=input_path,
        targets=target_filenames,
        scores=scores,
        num_results=num_results,
        show_scores=show_scores,
        id_links=id_links,
    )

    for entry in results:
        print(entry)


if __name__ == "__main__":
    main()
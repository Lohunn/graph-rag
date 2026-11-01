import os
import re
from pathlib import Path
from getpass import getpass

from neo4j import GraphDatabase


# ============================================================
# CONFIGURATION
# ============================================================

# Neo4j Desktop local database
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")

# Corpus folder
CORPUS_DIR = Path(__file__).parent / "corpus"


# ============================================================
# PARSER
# ============================================================

def parse_movie_file(file_path):
    """
    Parse one movie TXT file generated for this project.

    Expected structure:

    MOVIE ID: m001
    TITLE: Inception
    YEAR: 2010
    GENRES: Sci-Fi, Thriller
    COUNTRY: United States

    DIRECTOR:
    Christopher Nolan

    WRITER:
    Christopher Nolan

    CAST:
    - Leonardo DiCaprio
    - Joseph Gordon-Levitt

    PLOT:
    ...

    THEMES:
    - dreams
    - reality

    RELATED MOVIES:
    - Interstellar

    KNOWLEDGE GRAPH RELATIONSHIPS:
    - Christopher Nolan -> DIRECTED -> Inception
    ...
    """

    text = file_path.read_text(encoding="utf-8")

    lines = [line.rstrip() for line in text.splitlines()]

    movie = {
        "id": None,
        "title": None,
        "year": None,
        "genres": [],
        "country": None,
        "director": None,
        "writers": [],
        "cast": [],
        "plot": None,
        "themes": [],
        "related_movies": [],
    }

    # --------------------------------------------------------
    # Simple fields
    # --------------------------------------------------------

    for line in lines:

        if line.startswith("MOVIE ID:"):
            movie["id"] = line.replace("MOVIE ID:", "").strip()

        elif line.startswith("TITLE:"):
            movie["title"] = line.replace("TITLE:", "").strip()

        elif line.startswith("YEAR:"):
            year_text = line.replace("YEAR:", "").strip()

            try:
                movie["year"] = int(year_text)
            except ValueError:
                movie["year"] = None

        elif line.startswith("GENRES:"):
            genres_text = line.replace("GENRES:", "").strip()

            movie["genres"] = [
                g.strip()
                for g in genres_text.split(",")
                if g.strip()
            ]

        elif line.startswith("COUNTRY:"):
            movie["country"] = line.replace("COUNTRY:", "").strip()

    # --------------------------------------------------------
    # Section parser
    # --------------------------------------------------------

    sections = {}

    current_section = None

    for line in lines:

        stripped = line.strip()

        # Detect section headers
        if stripped in {
            "DIRECTOR:",
            "WRITER:",
            "CAST:",
            "PLOT:",
            "THEMES:",
            "RELATED MOVIES:",
            "KNOWLEDGE GRAPH RELATIONSHIPS:",
        }:
            current_section = stripped[:-1]
            sections[current_section] = []
            continue

        if current_section:
            sections[current_section].append(stripped)

    # --------------------------------------------------------
    # Director
    # --------------------------------------------------------

    if "DIRECTOR" in sections:

        director_lines = [
            x for x in sections["DIRECTOR"]
            if x
        ]

        if director_lines:
            movie["director"] = director_lines[0]

    # --------------------------------------------------------
    # Writers
    # --------------------------------------------------------

    if "WRITER" in sections:

        writer_lines = [
            x for x in sections["WRITER"]
            if x
        ]

        if writer_lines:

            # Writers are stored as:
            #
            # Christopher Nolan, Jonathan Nolan
            #
            # Split by comma.

            writer_text = " ".join(writer_lines)

            movie["writers"] = [
                w.strip()
                for w in writer_text.split(",")
                if w.strip()
            ]

    # --------------------------------------------------------
    # Cast
    # --------------------------------------------------------

    if "CAST" in sections:

        movie["cast"] = [
            re.sub(r"^- ", "", x).strip()
            for x in sections["CAST"]
            if x
        ]

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    if "PLOT" in sections:

        plot_lines = [
            x for x in sections["PLOT"]
            if x
        ]

        movie["plot"] = " ".join(plot_lines)

    # --------------------------------------------------------
    # Themes
    # --------------------------------------------------------

    if "THEMES" in sections:

        movie["themes"] = [
            re.sub(r"^- ", "", x).strip()
            for x in sections["THEMES"]
            if x
        ]

    # --------------------------------------------------------
    # Related Movies
    # --------------------------------------------------------

    if "RELATED MOVIES" in sections:

        movie["related_movies"] = [
            re.sub(r"^- ", "", x).strip()
            for x in sections["RELATED MOVIES"]
            if x
        ]

    return movie


# ============================================================
# NEO4J DATABASE SETUP
# ============================================================

def create_constraints(driver):

    queries = [

        """
        CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
        FOR (m:Movie)
        REQUIRE m.id IS UNIQUE
        """,

        """
        CREATE CONSTRAINT person_name_unique IF NOT EXISTS
        FOR (p:Person)
        REQUIRE p.name IS UNIQUE
        """,

        """
        CREATE CONSTRAINT genre_name_unique IF NOT EXISTS
        FOR (g:Genre)
        REQUIRE g.name IS UNIQUE
        """,

        """
        CREATE CONSTRAINT country_name_unique IF NOT EXISTS
        FOR (c:Country)
        REQUIRE c.name IS UNIQUE
        """,

        """
        CREATE CONSTRAINT theme_name_unique IF NOT EXISTS
        FOR (t:Theme)
        REQUIRE t.name IS UNIQUE
        """
    ]

    with driver.session() as session:

        for query in queries:
            session.run(query)

    print("✓ Neo4j constraints created.")


# ============================================================
# INSERT MOVIE
# ============================================================

def insert_movie(tx, movie):

    query = """
    MERGE (m:Movie {id: $id})

    SET
        m.title = $title,
        m.year = $year,
        m.plot = $plot

    RETURN m
    """

    tx.run(
        query,
        id=movie["id"],
        title=movie["title"],
        year=movie["year"],
        plot=movie["plot"],
    )


# ============================================================
# INSERT DIRECTOR
# ============================================================

def insert_director(tx, movie):

    if not movie["director"]:
        return

    query = """
    MATCH (m:Movie {id: $movie_id})

    MERGE (p:Person {name: $director})

    MERGE (p)-[:DIRECTED]->(m)
    """

    tx.run(
        query,
        movie_id=movie["id"],
        director=movie["director"],
    )


# ============================================================
# INSERT WRITERS
# ============================================================

def insert_writers(tx, movie):

    query = """
    MATCH (m:Movie {id: $movie_id})

    MERGE (p:Person {name: $writer})

    MERGE (p)-[:WROTE]->(m)
    """

    for writer in movie["writers"]:

        tx.run(
            query,
            movie_id=movie["id"],
            writer=writer,
        )


# ============================================================
# INSERT ACTORS
# ============================================================

def insert_cast(tx, movie):

    query = """
    MATCH (m:Movie {id: $movie_id})

    MERGE (p:Person {name: $actor})

    MERGE (p)-[:ACTED_IN]->(m)
    """

    for actor in movie["cast"]:

        tx.run(
            query,
            movie_id=movie["id"],
            actor=actor,
        )


# ============================================================
# INSERT GENRES
# ============================================================

def insert_genres(tx, movie):

    query = """
    MATCH (m:Movie {id: $movie_id})

    MERGE (g:Genre {name: $genre})

    MERGE (m)-[:HAS_GENRE]->(g)
    """

    for genre in movie["genres"]:

        tx.run(
            query,
            movie_id=movie["id"],
            genre=genre,
        )


# ============================================================
# INSERT COUNTRY
# ============================================================

def insert_country(tx, movie):

    if not movie["country"]:
        return

    query = """
    MATCH (m:Movie {id: $movie_id})

    MERGE (c:Country {name: $country})

    MERGE (m)-[:FROM_COUNTRY]->(c)
    """

    tx.run(
        query,
        movie_id=movie["id"],
        country=movie["country"],
    )


# ============================================================
# INSERT THEMES
# ============================================================

def insert_themes(tx, movie):

    query = """
    MATCH (m:Movie {id: $movie_id})

    MERGE (t:Theme {name: $theme})

    MERGE (m)-[:HAS_THEME]->(t)
    """

    for theme in movie["themes"]:

        tx.run(
            query,
            movie_id=movie["id"],
            theme=theme,
        )


# ============================================================
# INSERT MOVIE-TO-MOVIE RELATIONSHIPS
# ============================================================

def insert_related_movies(tx, movie):

    query = """
    MATCH (m1:Movie {id: $movie_id})
    MATCH (m2:Movie {title: $related_title})

    MERGE (m1)-[:THEMATICALLY_RELATED_TO]->(m2)
    """

    for related_movie in movie["related_movies"]:

        tx.run(
            query,
            movie_id=movie["id"],
            related_title=related_movie,
        )


# ============================================================
# INGEST ONE MOVIE
# ============================================================

def ingest_movie(driver, movie):

    with driver.session() as session:

        session.execute_write(
            insert_movie,
            movie
        )

        session.execute_write(
            insert_director,
            movie
        )

        session.execute_write(
            insert_writers,
            movie
        )

        session.execute_write(
            insert_cast,
            movie
        )

        session.execute_write(
            insert_genres,
            movie
        )

        session.execute_write(
            insert_country,
            movie
        )

        session.execute_write(
            insert_themes,
            movie
        )


# ============================================================
# INSERT RELATED MOVIES AFTER ALL MOVIES EXIST
# ============================================================

def ingest_relationships(driver, movies):

    with driver.session() as session:

        for movie in movies:

            session.execute_write(
                insert_related_movies,
                movie
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("       MOVIE GRAPH RAG - NEO4J INGESTION")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # Check corpus directory
    # --------------------------------------------------------

    if not CORPUS_DIR.exists():

        print("ERROR: corpus folder was not found.")

        print()
        print("Expected:")
        print(CORPUS_DIR)

        return

    txt_files = sorted(CORPUS_DIR.glob("*.txt"))

    if not txt_files:

        print("ERROR: No .txt files found in corpus folder.")

        return

    print(f"Found {len(txt_files)} text files.")
    print()

    # --------------------------------------------------------
    # Read Neo4j password
    # --------------------------------------------------------

    password = os.getenv("NEO4J_PASSWORD")

    if not password:

        password = getpass(
            "Enter your Neo4j password: "
        )

    print()
    print("Connecting to Neo4j...")
    print(f"URI: {NEO4J_URI}")
    print(f"User: {NEO4J_USER}")
    print()

    # --------------------------------------------------------
    # Connect
    # --------------------------------------------------------

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, password)
    )

    try:

        driver.verify_connectivity()

        print("✓ Connected to Neo4j.")
        print()

        # ----------------------------------------------------
        # Create constraints
        # ----------------------------------------------------

        create_constraints(driver)

        print()

        # ----------------------------------------------------
        # Parse all files FIRST
        # ----------------------------------------------------

        movies = []

        for file_path in txt_files:

            print(f"Reading: {file_path.name}")

            try:

                movie = parse_movie_file(file_path)

                # Validate
                if not movie["id"]:
                    print("  WARNING: Missing movie ID")

                if not movie["title"]:
                    print("  WARNING: Missing title")

                movies.append(movie)

            except Exception as e:

                print(
                    f"  ERROR parsing {file_path.name}: {e}"
                )

        print()
        print(f"Successfully parsed {len(movies)} movies.")
        print()

        # ----------------------------------------------------
        # Insert movies
        # ----------------------------------------------------

        print("Creating movie graph...")
        print()

        for index, movie in enumerate(movies, start=1):

            print(
                f"[{index}/{len(movies)}] "
                f"{movie['title']}"
            )

            ingest_movie(
                driver,
                movie
            )

        print()
        print("✓ Movie nodes and direct relationships created.")
        print()

        # ----------------------------------------------------
        # Movie-to-movie relationships
        # ----------------------------------------------------

        print(
            "Creating movie-to-movie relationships..."
        )

        ingest_relationships(
            driver,
            movies
        )

        print()
        print("✓ Movie relationships created.")
        print()

        # ----------------------------------------------------
        # Final statistics
        # ----------------------------------------------------

        with driver.session() as session:

            result = session.run(
                """
                MATCH (n)
                RETURN labels(n) AS label,
                       count(n) AS count
                ORDER BY label
                """
            )

            print("=" * 60)
            print("NODE COUNTS")
            print("=" * 60)

            for record in result:

                print(
                    f"{record['label']}: "
                    f"{record['count']}"
                )

            print()

            result = session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS relationship,
                       count(r) AS count
                ORDER BY relationship
                """
            )

            print("=" * 60)
            print("RELATIONSHIP COUNTS")
            print("=" * 60)

            for record in result:

                print(
                    f"{record['relationship']}: "
                    f"{record['count']}"
                )

        print()
        print("=" * 60)
        print("       INGESTION COMPLETE!")
        print("=" * 60)
        print()

    except Exception as e:

        print()
        print("ERROR:")
        print(e)
        print()

    finally:

        driver.close()

        print("Neo4j connection closed.")


# ============================================================
# RUN PROGRAM
# ============================================================

if __name__ == "__main__":
    main()
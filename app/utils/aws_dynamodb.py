import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any

from config import DYNAMODB_TABLE
import logging


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
movies_table = dynamodb.Table(f"{DYNAMODB_TABLE}-movies")
comments_table = dynamodb.Table(f"{DYNAMODB_TABLE}-comments")
ratings_table = dynamodb.Table(f"{DYNAMODB_TABLE}-ratings")

dynamodb = boto3.resource("dynamodb")


def put_movie(movie_data):
    movies_table.put_item(Item=movie_data)


def get_movie(movie_id):
    response = movies_table.get_item(Key={"id": movie_id})
    return response.get("Item")


def delete_movie(movie_id):
    movies_table.delete_item(Key={"id": movie_id})


def update_movie(movie_id, updated_data):
    update_expression = "SET " + ", ".join(f"{k}=:{k}" for k in updated_data.keys())
    expression_attribute_values = {f":{k}": v for k, v in updated_data.items()}
    movies_table.update_item(
        Key={"id": movie_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
    )
    return get_movie(movie_id)


def query_movies_by_rating(min_rating):
    response = ratings_table.scan(
        FilterExpression=Key("rating").gte(min_rating)
    )
    return response.get("Items", [])


def query_movies_by_genre(genre):
    response = movies_table.query(
        IndexName="GenreIndex",
        KeyConditionExpression=Key("genre").eq(genre)
    )
    return response.get("Items", [])


# Comment and rating functions
def put_comment(comment_data):
    comments_table.put_item(Item=comment_data)


def get_comment(comment_id):
    response = comments_table.get_item(Key={"id": comment_id})
    return response.get("Item")


def update_comment(comment_id, updated_data):
    update_expression = "SET " + ", ".join(f"{k}=:{k}" for k in updated_data.keys())
    expression_attribute_values = {f":{k}": v for k, v in updated_data.items()}
    comments_table.update_item(
        Key={"id": comment_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
    )


def get_comments_by_movie(movie_id):
    response = comments_table.query(
        IndexName="MovieIndex",
        KeyConditionExpression=Key("movie_id").eq(movie_id)
    )
    return response.get("Items", [])


def add_rating(movie_id, user_id, rating):
    ratings_table.put_item(Item={
        "movie_id": movie_id,
        "user_id": user_id,
        "rating": rating
    })
    update_movie_rating(movie_id)


def update_movie_rating(movie_id):
    response = ratings_table.query(
        KeyConditionExpression=Key("movie_id").eq(movie_id)
    )
    ratings = [item["rating"] for item in response.get("Items", [])]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
    ratings_table.update_item(
        Key={"id": movie_id},
        UpdateExpression="SET rating = :rating",
        ExpressionAttributeValues={":rating": avg_rating},
    )


def scan_movies() -> List[Dict[str, Any]]:
    """Get all movies from the database"""
    try:
        response = movies_table.scan()
        movies = response.get('Items', [])

        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = movies_table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            movies.extend(response.get('Items', []))

        return movies
    except Exception as e:
        logger.error(f"Error scanning movies: {e}")
        raise


def get_movies_by_user(user_id: int) -> List[Dict[str, Any]]:
    """Get all movies uploaded by a specific user"""
    try:
        response = movies_table.query(
            IndexName='UserIndex',
            KeyConditionExpression=Key('user_id').eq(user_id)
        )
        return [movie for movie in response.get('Items', [])]
    except Exception as e:
        logger.error(f"Error getting movies for user {user_id}: {e}")
        raise


def get_movie_ratings(movie_id: str) -> Dict[str, Any]:
    """Get rating statistics for a movie"""
    try:
        response = ratings_table.query(
            KeyConditionExpression=Key('movie_id').eq(movie_id)
        )
        ratings = [float(item['rating']) for item in response.get('Items', [])]

        if not ratings:
            return {
                'average': 0.0,
                'count': 0,
                'distribution': {str(i): 0 for i in range(1, 11)}
            }

        # Calculate rating distribution
        distribution = {str(i): 0 for i in range(1, 11)}
        for rating in ratings:
            distribution[str(int(rating))] += 1

        return {
            'average': sum(ratings) / len(ratings),
            'count': len(ratings),
            'distribution': distribution
        }
    except Exception as e:
        logger.error(f"Error getting ratings for movie {movie_id}: {e}")
        raise


def get_user_rating(movie_id: str, user_id: int) -> float:
    """Get a user's rating for a specific movie"""
    try:
        response = ratings_table.get_item(
            Key={
                'movie_id': movie_id,
                'user_id': user_id
            }
        )
        item = response.get('Item')
        return float(item['rating']) if item else None
    except Exception as e:
        logger.error(f"Error getting user {user_id} rating for movie {movie_id}: {e}")
        raise


def add_rating(movie_id: str, user_id: int, rating: float) -> None:
    """Add or update a user's rating for a movie"""
    try:
        # Add rating to ratings table
        ratings_table.put_item(
            Item={
                'movie_id': movie_id,
                'user_id': user_id,
                'rating': Decimal(str(rating)),
                'timestamp': datetime.utcnow().isoformat()
            }
        )

        # Update average rating in movies table
        ratings_stats = get_movie_ratings(movie_id)
        movies_table.update_item(
            Key={'id': movie_id},
            UpdateExpression='SET rating = :r',
            ExpressionAttributeValues={
                ':r': Decimal(str(ratings_stats['average']))
            }
        )
    except Exception as e:
        logger.error(f"Error adding rating for movie {movie_id}: {e}")
        raise


def add_comment(movie_id: str, user_id: int, content: str) -> Dict[str, Any]:
    """Add a comment to a movie"""
    try:
        comment_data = {
            'id': f"{movie_id}_{datetime.utcnow().timestamp()}",
            'movie_id': movie_id,
            'user_id': user_id,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }

        comments_table.put_item(Item=comment_data)
        return comment_data
    except Exception as e:
        logger.error(f"Error adding comment for movie {movie_id}: {e}")
        raise


def update_comment(comment_id: str, content: str) -> Dict[str, Any]:
    """Update a comment"""
    try:
        comments_table.update_item(
            Key={'id': comment_id},
            UpdateExpression='SET content = :c, updated_at = :u',
            ExpressionAttributeValues={
                ':c': content,
                ':u': datetime.utcnow().isoformat()
            },
            ReturnValues='ALL_NEW'
        )
        return get_comment(comment_id)
    except Exception as e:
        logger.error(f"Error updating comment {comment_id}: {e}")
        raise


def delete_comment(comment_id: str) -> None:
    """Delete a comment"""
    try:
        comments_table.delete_item(Key={'id': comment_id})
    except Exception as e:
        logger.error(f"Error deleting comment {comment_id}: {e}")
        raise


def get_comment(comment_id: str) -> Dict[str, Any]:
    """Get a specific comment"""
    try:
        response = comments_table.get_item(Key={'id': comment_id})
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting comment {comment_id}: {e}")
        raise


def get_comments_by_movie(movie_id: str) -> List[Dict[str, Any]]:
    """Get all comments for a movie"""
    try:
        response = comments_table.query(
            IndexName='MovieIndex',
            KeyConditionExpression=Key('movie_id').eq(movie_id),
            ScanIndexForward=False  # Sort by timestamp descending
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error getting comments for movie {movie_id}: {e}")
        raise


def get_comments_by_user(user_id: int) -> List[Dict[str, Any]]:
    """Get all comments by a user"""
    try:
        response = comments_table.query(
            IndexName='UserIndex',
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False  # Sort by timestamp descending
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error getting comments for user {user_id}: {e}")
        raise


def create_tables() -> None:
    """Create DynamoDB tables if they don't exist"""
    try:
        # Movies table
        movies_table = dynamodb.create_table(
            TableName=f"{DYNAMODB_TABLE}-movies",
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'N'},
                {'AttributeName': 'genre', 'AttributeType': 'S'},
                {'AttributeName': 'rating', 'AttributeType': 'N'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'UserIndex',
                    'KeySchema': [{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'GenreIndex',
                    'KeySchema': [{'AttributeName': 'genre', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'RatingIndex',
                    'KeySchema': [{'AttributeName': 'rating', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        # Comments table
        comments_table = dynamodb.create_table(
            TableName=f"{DYNAMODB_TABLE}-comments",
            KeySchema=[
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'movie_id', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'N'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'MovieIndex',
                    'KeySchema': [{'AttributeName': 'movie_id', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'UserIndex',
                    'KeySchema': [{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        # Ratings table
        ratings_table = dynamodb.create_table(
            TableName=f"{DYNAMODB_TABLE}-ratings",
            KeySchema=[
                {'AttributeName': 'movie_id', 'KeyType': 'HASH'},
                {'AttributeName': 'user_id', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'movie_id', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'N'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        logger.info("Created DynamoDB tables successfully")
    except Exception as e:
        logger.error(f"Error creating DynamoDB tables: {e}")
        raise


if __name__ == "__main__":
    create_tables()
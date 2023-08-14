from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from forms import CreateBlogPostForm, RegistrationForm, LoginForm, CommentForm
import os

# Create flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY")
#print(app.config['SECRET_KEY'])
# Configure CKEditor
ckeditor = CKEditor(app)
# Configure Bootstrap5
Bootstrap5(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)




# For adding profile images to the comment section we configure Flask-Gravatar
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

# Connect to Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_LOCATION", "sqlite:///posts.db")

#print(os.environ.get("DATABASE_LOCATION").strip("[]"))

database = SQLAlchemy()
database.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return database.get_or_404(User, user_id)

# Configure database tables

# Create BlogPost table

class BlogPost(database.Model):
    __tablename__ = "blog_posts"
    id = database.Column(database.Integer, primary_key=True)
    # Create Foreign Key, "users.id" the users refers to the tablename of User.
    author_id = database.Column(database.Integer, database.ForeignKey("users.id"))
    # Create reference to the User object. The "posts" refers to the posts property in the User class.
    author = relationship("User", back_populates="posts")
    title = database.Column(database.String(250), unique=True, nullable=False)
    subtitle = database.Column(database.String(250), nullable=False)
    date = database.Column(database.String(250), nullable=False)
    body = database.Column(database.Text, nullable=False)
    img_url = database.Column(database.String(250), nullable=False)
    # Parent relationship to the comments
    comments = relationship("Comment", back_populates="parent_post")


# Create the User table

class User(UserMixin, database.Model):
    __tablename__ = "users"
    id = database.Column(database.Integer, primary_key=True)
    email = database.Column(database.String(100), unique=True)
    password = database.Column(database.String(100))
    name = database.Column(database.String(100))
    # This will act like a list of BlogPost objects attached to each User.
    # The "author" refers to the author property in the BlogPost class.
    posts = relationship("BlogPost", back_populates="author")
    # Parent relationship: "comment_author" refers to the comment_author property in the Comment class.
    comments = relationship("Comment", back_populates="comment_author")


# Create the BlogPost comments table
class Comment(database.Model):
    __tablename__ = "comments"
    id = database.Column(database.Integer, primary_key=True)
    text = database.Column(database.Text, nullable=False)
    # Child relationship:"users.id" The users refers to the tablename of the User class.
    # "comments" refers to the comments property in the User class.
    author_id = database.Column(database.Integer, database.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")
    # Child Relationship to the BlogPosts
    post_id = database.Column(database.Integer, database.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")


with app.app_context():
    database.create_all()


# Create a decorator function that allows only the administrator
def admin_only(function_to_be_passed):
    @wraps(function_to_be_passed)
    def decorated_function(*args, **kwargs):
        # If id is not 1 then return abort with 403 error
        if current_user.id != 1:
            return abort(403)
        # Otherwise continue with the route function
        return function_to_be_passed(*args, **kwargs)

    return decorated_function


# Register new users new users
@app.route('/register', methods=["GET", "POST"])
def register():
    registration_form = RegistrationForm()
    if registration_form.validate_on_submit():

        # Is user already in the database?
        result = database.session.execute(database.select(User).where(User.email == registration_form.email.data))
        user = result.scalar()
        if user:
            # User already exists
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hash_and_salted_password = generate_password_hash(
            registration_form.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=registration_form.email.data,
            name=registration_form.name.data,
            password=hash_and_salted_password,
        )
        database.session.add(new_user)
        database.session.commit()
        # This line will authenticate the user with Flask-Login
        login_user(new_user)
        return redirect(url_for("get_all_posts"))
    return render_template("register.html", form=registration_form, current_user=current_user)


@app.route('/login', methods=["GET", "POST"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        password = login_form.password.data
        result = database.session.execute(database.select(User).where(User.email == login_form.email.data))
        # Note, email in db is unique so will only have one result.
        user = result.scalar()
        # Email doesn't exist
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        # Password incorrect
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('get_all_posts'))

    return render_template("login.html", form=login_form, current_user=current_user)


# logout user
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


# home route
@app.route('/')
def get_all_posts():
    result = database.session.execute(database.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


# Add a POST method to be able to post comments
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = database.get_or_404(BlogPost, post_id)
    # Add the CommentForm to the route
    comment_form = CommentForm()
    # Only allow logged-in users to comment on posts
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for("login"))

        new_comment = Comment(
            text=comment_form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        database.session.add(new_comment)
        database.session.commit()
    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form)


# Use a decorator so only an admin user can create new posts
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    create_blog_post_form = CreateBlogPostForm()
    if create_blog_post_form.validate_on_submit():
        new_post = BlogPost(
            title=create_blog_post_form.title.data,
            subtitle=create_blog_post_form.subtitle.data,
            body=create_blog_post_form.body.data,
            img_url=create_blog_post_form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        database.session.add(new_post)
        database.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=create_blog_post_form, current_user=current_user)


# Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    post = database.get_or_404(BlogPost, post_id)
    edit_form = CreateBlogPostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        database.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


# Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = database.get_or_404(BlogPost, post_id)
    database.session.delete(post_to_delete)
    database.session.commit()
    return redirect(url_for('get_all_posts'))


# route to about page
@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


# route to contact page
@app.route("/contact", methods=["GET", "POST"])
def contact():
    return render_template("contact.html", current_user=current_user)


if __name__ == "__main__":
    app.run(debug=False)
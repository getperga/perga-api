from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.helpers.browser_session_helper import BrowserSessionHelper
from app.schemas.auth import TokenSchema, SigninSchema, RefreshTokenSchema, GoogleSigninSchema
from app.schemas.user import UserSchema, UserCreateSchema, UserUpdateSchema, PasswordChangeSchema
from app.services.user_service import UserService
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/signup/", response_model=UserSchema)
def signup(request_data: UserCreateSchema, db: Session = Depends(get_db)):
    if settings.IS_SIGNUP_DISABLED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signup is disabled")

    try:
        user = UserService.create_user(db=db, create_data=request_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return user


@router.post("/access_token/", response_model=TokenSchema)
def get_access_token(
    response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
):
    """ Get an access token using username and password """
    user = AuthService.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return BrowserSessionHelper.prepare_tokens_response(response, AuthService.create_user_tokens(db, user), None)


@router.post("/access_token_json/", response_model=TokenSchema)
def get_access_token_json(
    signin_data: SigninSchema, request: Request, response: Response, db: Session = Depends(get_db),
):
    """ Get access token using JSON instead of form data """
    origin = BrowserSessionHelper.get_browser_origin(request)
    user = AuthService.authenticate_user(db, signin_data.username, signin_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if origin:
        AuthService.revoke_session(db, BrowserSessionHelper.get_submitted_refresh_token(request, None))

    return BrowserSessionHelper.prepare_tokens_response(response, AuthService.create_user_tokens(db, user), origin)


@router.post("/refresh_token/", response_model=TokenSchema)
def refresh_access_token(
    request: Request, response: Response,
    refresh_request: RefreshTokenSchema | None = None, db: Session = Depends(get_db),
):
    """ Get a new access token using a refresh token """
    refresh_token = BrowserSessionHelper.get_submitted_refresh_token(request, refresh_request)
    tokens = AuthService.refresh_user_tokens(db, refresh_token)
    response.headers['Cache-Control'] = 'no-store'

    if request.headers.get(BrowserSessionHelper.BROWSER_SESSION_HEADER) == BrowserSessionHelper.BROWSER_SESSION_VALUE:
        tokens['refresh_token'] = None

    return tokens


@router.post("/logout/", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, response: Response,
    refresh_request: RefreshTokenSchema | None = None, db: Session = Depends(get_db),
):
    AuthService.revoke_session(db, BrowserSessionHelper.get_submitted_refresh_token(request, refresh_request))
    origin = BrowserSessionHelper.get_browser_origin(request)
    if not origin:
        return

    name, path, secure = BrowserSessionHelper.get_browser_cookie(origin)
    response.delete_cookie(name, path=path, secure=secure, httponly=True, samesite='lax')


@router.get("/user/", response_model=UserSchema)
def get_current_user(current_user: UserSchema = Depends(AuthService.get_current_user)):
    return current_user


@router.put("/user/", response_model=UserSchema)
def update_user(
    request_data: UserUpdateSchema,
    current_user: UserSchema = Depends(AuthService.get_current_user),
    db: Session = Depends(get_db)
):
    updated_user = UserService.update_user(db=db, user_id=current_user.id, update_data=request_data)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return updated_user


@router.put("/user/password/", response_model=UserSchema)
def change_password(
    password_change: PasswordChangeSchema,
    current_user: UserSchema = Depends(AuthService.get_current_user),
    db: Session = Depends(get_db)
):
    try:
        updated_user = UserService.change_password(
            db=db,
            user_id=current_user.id,
            current_password=password_change.current_password,
            new_password=password_change.new_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return updated_user


@router.post('/google/', response_model=TokenSchema)
def google_signin(
    signin_data: GoogleSigninSchema, request: Request, response: Response, db: Session = Depends(get_db),
):
    origin = BrowserSessionHelper.get_browser_origin(request)
    token_info = AuthService.exchange_google_code(signin_data.code)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid Google auth code',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    google_id = token_info.get('sub')
    email = token_info.get('email')
    if not google_id or not email or token_info.get('email_verified') is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing information in Google token'
        )

    user = UserService.get_or_create_google_user(db=db, google_id=google_id, email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found'
        )

    if origin:
        AuthService.revoke_session(db, BrowserSessionHelper.get_submitted_refresh_token(request, None))

    return BrowserSessionHelper.prepare_tokens_response(response, AuthService.create_user_tokens(db, user), origin)
